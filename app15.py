import streamlit as st
import pandas as pd
import datetime
import pytz
import firebase_admin
from firebase_admin import auth, credentials, firestore, exceptions

# Inject custom CSS for RTL
rtl_css = """
<style>
    body {
        direction: rtl;
        text-align: right;
    }
    .streamlit-expanderHeader, .streamlit-radio {
        direction: rtl;
        text-align: right;
    }
    table, th, td {
        direction: rtl;
        text-align: right;
    }
</style>
"""
st.markdown(rtl_css, unsafe_allow_html=True)

##############################
#      TIME WINDOW CHECK     #
##############################
def can_show_riddle():
    local_tz = pytz.timezone("Asia/Riyadh")
    now = datetime.datetime.now(local_tz)
    start_time = now.replace(hour=19, minute=0, second=0, microsecond=0)  
    end_time = now.replace(hour=19, minute=5, second=0, microsecond=0)  
    return start_time <= now <= end_time

##############################
#         FIREBASE INIT      #
##############################
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

##############################
#       MANUAL RIDDLE        #
##############################
# 🎯 Every day, update this section with a new riddle before uploading
RIDDLE = {
    "question": "ما هو أكبر حيوان عاش على الأرض مطلقًا؟",
    "options": ["الحوت الأزرق", "الفيل الأفريقي", "الأباتوصور", "السبينوصور"],
    "answer": "الحوت الأزرق"
}

##############################
#      USER AUTH SECTION     #
##############################
st.title("🌙 فوازير رمضان")

email = st.text_input("📧 أدخل البريد الإلكتروني:")
password = st.text_input("🔑 أدخل كلمة المرور:", type="password")

if st.button("تسجيل الدخول"):
    try:
        user = auth.get_user_by_email(email)
        st.session_state.uid = user.uid
        st.session_state.email = user.email  
        user_ref = db.collection("users").document(user.uid)
        user_ref.set({"email": user.email}, merge=True)
        st.success("✅ تم تسجيل الدخول بنجاح!")
    except exceptions.NotFoundError:
        st.error("❌ البريد الإلكتروني غير مسجل. الرجاء إنشاء حساب جديد.")

if st.button("إنشاء حساب جديد"):
    try:
        user = auth.create_user(email=email, password=password)
        st.session_state.uid = user.uid
        st.session_state.email = email
        db.collection("users").document(user.uid).set({
            "email": email,
            "points": 0,
            "answered_date": "",
            "answered_correctly_today": False
        })
        st.success("🎉 تم إنشاء الحساب بنجاح!")
    except exceptions.FirebaseError as e:
        st.error(f"❌ خطأ: {e}")

##############################
#      MAIN QUIZ SECTION     #
##############################
if 'uid' in st.session_state:
    st.subheader("حاول حل الفزورة اليومية واربح النقاط!")

    user_ref = db.collection("users").document(st.session_state.uid)
    doc = user_ref.get()
    
    if doc.exists:
        user_data = doc.to_dict()
        current_points = user_data.get("points", 0)
        answered_date = user_data.get("answered_date", "")
        answered_correctly_today = user_data.get("answered_correctly_today", False)
    else:
        current_points = 0
        answered_date = ""
        answered_correctly_today = False
        user_ref.set({
            "email": st.session_state.email,
            "points": 0,
            "answered_date": "",
            "answered_correctly_today": False
        })

    today_str = str(datetime.date.today())

    if can_show_riddle():
        st.info("الوقت مفتوح الآن للإجابة: من ٧:٠٠ إلى ٧:٠٥ مساءً.")

        if answered_date == today_str:
            st.warning("لقد أجبت اليوم بالفعل! عد غدًا لفزورة جديدة.")
        else:
            st.write("### فزورة اليوم:")
            st.write(RIDDLE["question"])
            chosen = st.radio("اختر الإجابة:", RIDDLE["options"], index=0)

            if st.button("تحقق من الإجابة"):
                is_correct = (chosen == RIDDLE["answer"])
                
                if is_correct:
                    st.success("✅ إجابة صحيحة!")

                    # Count previous correct answers today
                    correct_query = db.collection("users")\
                        .where("answered_date", "==", today_str)\
                        .where("answered_correctly_today", "==", True)
                    correct_docs = correct_query.get()
                    correct_count = len(correct_docs)

                    # Assign points based on the rank
                    if correct_count == 0:
                        add_points = 15
                    elif correct_count == 1:
                        add_points = 10
                    elif correct_count == 2:
                        add_points = 5
                    else:
                        add_points = 3  # All other correct answers get 3 points

                else:
                    st.error("❌ إجابة خاطئة! ولكنك حصلت على نقطة واحدة.")
                    add_points = 1  # Wrong answer gets 1 point

                # Update points
                new_points = current_points + add_points
                user_ref.update({
                    "points": new_points,
                    "answered_date": today_str,
                    "answered_correctly_today": is_correct
                })
                st.success(f"🎉 حصلت على {add_points} نقطة إضافية!")
    
    else:
        st.warning("عذرًا! لا يمكنك الإجابة الآن. سيمكنك الإجابة من ٧:٠٠ إلى ٧:٠٥ مساءً.")

    ##############################
    #        LEADERBOARD         #
    ##############################
    st.header("🏆 لوحة الصدارة")

    lb_query = db.collection("users").order_by("points", direction=firestore.Query.DESCENDING).limit(10)
    lb_docs = lb_query.get()

    rows = []
    rank = 1
    user_position = None
    for d in lb_docs:
        info = d.to_dict()
        email_display = info.get("email", "مجهول")
        points_val = info.get("points", 0)
        rows.append([rank, email_display, points_val])

        if d.id == st.session_state.uid:
            user_position = rank
        rank += 1

    df = pd.DataFrame(rows, columns=["المركز", "البريد الإلكتروني", "النقاط"])
    st.table(df)

    if user_position:
        st.write(f"ترتيبك الحالي في لوحة الصدارة هو: #{user_position}")
    else:
        st.write("أنت خارج أفضل 10.") 
