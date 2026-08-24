import os
import requests

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_otp_email(to_email: str, otp: str, firstname: str = "") -> bool:
    """
    Send OTP email using the Brevo REST API.

    Returns:
        True  -> Email sent successfully
        False -> Failed to send
    """

    api_key = os.getenv("BREVO_API_KEY")
    from_email = os.getenv("FROM_EMAIL")
    from_name = os.getenv("FROM_NAME", "ZigZag")

    if not api_key:
        print("[email_service] ERROR: BREVO_API_KEY is missing")
        return False

    if not from_email:
        print("[email_service] ERROR: FROM_EMAIL is missing")
        return False

    greeting = f"Hi {firstname}," if firstname else "Hi,"

    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:24px">
        <h2 style="color:#111827;">Verify your email</h2>

        <p>{greeting}</p>

        <p>Your verification code is:</p>

        <div style="
            font-size:34px;
            font-weight:bold;
            letter-spacing:8px;
            text-align:center;
            background:#f3f4f6;
            padding:18px;
            border-radius:8px;
            margin:24px 0;
        ">
            {otp}
        </div>

        <p>This code expires in <strong>15 minutes</strong>.</p>

        <p>If you didn't request this code, you can safely ignore this email.</p>

        <br>

        <p>— ZigZag Team</p>
    </div>
    """

    payload = {
        "sender": {
            "name": from_name,
            "email": from_email,
        },
        "to": [
            {
                "email": to_email,
                "name": firstname,
            }
        ],
        "subject": "Your ZigZag Verification Code",
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }

    try:
        response = requests.post(
            BREVO_API_URL,
            json=payload,
            headers=headers,
            timeout=20,
        )

        if response.status_code in (200, 201):
            print("[email_service] OTP email sent successfully.")
            return True

        print(
            "[email_service] Brevo API Error:",
            response.status_code,
            response.text,
        )
        return False

    except requests.exceptions.Timeout:
        print("[email_service] Request timed out.")
        return False

    except requests.exceptions.ConnectionError as e:
        print("[email_service] Connection error:", e)
        return False

    except Exception as e:
        print("[email_service] Unexpected error:", e)
        return False