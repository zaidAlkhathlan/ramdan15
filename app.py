import streamlit as st
import pandas as pd
import datetime
import pytz
import firebase_admin
from firebase_admin import auth, credentials, firestore, exceptions
import json
# Inject custom CSS for RTL
rtl_css = """
<style>
    /* Force RTL direction and right alignment */
    body {
        direction: rtl;
        text-align: right;
    }
    /* Also align radio buttons / checkboxes to the right */
    .streamlit-expanderHeader, .streamlit-radio {
        direction: rtl;
        text-align: right;
    }
    /* If you use table, set it to RTL, etc. */
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
    """
    Returns True if the current local time in Asia/Riyadh is between 7:00 PM and 7:05 PM.
    Otherwise, returns False.
    """
    local_tz = pytz.timezone("Asia/Riyadh")
    now = datetime.datetime.now(local_tz)

    # Debug info: show current local time

    # Define the allowed window: 7:00 PM → 7:05 PM
    start_time = now.replace(hour=21, minute=0, second=0, microsecond=0)  # 7:00 PM
    end_time   = now.replace(hour=21, minute=5, second=0, microsecond=0)  # 7:05 PM

    
    return start_time <= now <= end_time

##############################
#         FIREBASE INIT      #
##############################
if not firebase_admin._apps:
    # Load secrets from Streamlit
    cred = credentials.Certificate(json.loads(st.secrets["firebase"].to_json()))
    firebase_admin.initialize_app(cred)

db = firestore.client()

##############################
#       SAMPLE RIDDLES       #
##############################
RIDDLES = [
    {"question": "كم عدد السور المكيه في القران الكريم؟", "options": ["85", "88", "87", "90"], "answer": "85"},
    
]

##############################
#      USER AUTH SECTION     #
##############################
st.title("🌙 فوازير @@@@@رمضان")

email = st.text_input("📧 أدخل البريد الإلكتروني:")
password = st.text_input("🔑 أدخل كلمة المرور:", type="password")

if st.button("تسجيل الدخول"):
    try:
        user = auth.get_user_by_email(email)
        st.session_state.uid = user.uid
        st.session_state.email = user.email  # store user email in session
        # Ensure user doc has 'email' in Firestore
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
        # Initialize user doc
        db.collection("users").document(user.uid).set({
            "email": email,
            "points": 0,
            "answered_date": "",            # date of last answer
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

    # Load user from Firestore
    user_ref = db.collection("users").document(st.session_state.uid)
    doc = user_ref.get()
    if doc.exists:
        user_data = doc.to_dict()
        current_points = user_data.get("points", 0)
        answered_date  = user_data.get("answered_date", "")
        answered_correctly_today = user_data.get("answered_correctly_today", False)
    else:
        # If doc doesn't exist, create it
        current_points = 0
        answered_date  = ""
        answered_correctly_today = False
        user_ref.set({
            "email": st.session_state.email,
            "points": 0,
            "answered_date": "",
            "answered_correctly_today": False
        })

    # Pick today's riddle
    idx = datetime.date.today().day % len(RIDDLES)
    riddle = RIDDLES[idx]

    today_str = str(datetime.date.today())

    # --- Check the time window (7:00–7:05 PM) ---
    if can_show_riddle():
        st.info("الوقت مفتوح الآن للإجابة: من ٩:٠٠ إلى ٩:٠٥ مساءً.")

        if answered_date == today_str:
            # User already answered today
            st.warning("لقد أجبت اليوم بالفعل! عد غدًا لفزورة جديدة.")
        else:
            # Show today's riddle
            st.write("### فزورة اليوم:")
            st.write(riddle["question"])
            chosen = st.radio("اختر الإجابة:", riddle["options"], index=0)

            if st.button("تحقق من الإجابة"):
                is_correct = (chosen == riddle["answer"])
                if is_correct:
                    st.success("إجابة صحيحة!")

                    # Count how many have answered correctly so far TODAY
                    correct_query = db.collection("users")\
                        .where("answered_date", "==", today_str)\
                        .where("answered_correctly_today", "==", True)
                    correct_docs = correct_query.get()
                    correct_count = len(correct_docs)

                    # Decide how many points to award
                    if correct_count == 0:
                        add_points = 15
                    elif correct_count == 1:
                        add_points = 10
                    elif correct_count == 2:
                        add_points = 5
                    else:
                        add_points = 0  # beyond the 3rd correct user => no points

                    new_points = current_points + add_points
                    user_ref.update({
                        "points": new_points,
                        "answered_date": today_str,
                        "answered_correctly_today": True
                    })
                    st.success(f"حصلت على {add_points} نقطة إضافية!")
                else:
                    st.error("إجابة خاطئة! حاول مرة أخرى غدًا.")
                    user_ref.update({
                        "answered_date": today_str,
                        "answered_correctly_today": False
                    })

    else:
        st.warning("عذرًا! لا يمكنك الإجابة الآن.  سيمكنك الاجابه من ٩:٠٠ إلى ٩:٠٥ مساءً.")

    # -----------------------
    #     Leaderboard
    # -----------------------
    st.header("🏆 لوحة الصدارة")

    # Show top 10 by points desc
    lb_query = db.collection("users").order_by("points", direction=firestore.Query.DESCENDING).limit(10)
    lb_docs  = lb_query.get()

    rows = []
    rank = 1
    user_position = None
    for d in lb_docs:
        info = d.to_dict()
        email_display = info.get("email", "مجهول")
        points_val    = info.get("points", 0)
        rows.append([rank, email_display, points_val])

        if d.id == st.session_state.uid:
            user_position = rank
        rank += 1

    df = pd.DataFrame(rows, columns=["المركز","البريد الإلكتروني","النقاط"])
    st.table(df)

    if user_position:
        st.write(f"ترتيبك الحالي في لوحة الصدارة هو: #{user_position}")
    else:
        st.write("أنت خارج أفضل 10.")

