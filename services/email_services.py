import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_otp_email(to_email: str, otp: str, firstname: str = "") -> bool:
    """
    Sends the OTP verification email via plain SMTP.
    Returns True on success, False on failure (never raises — signup/resend
    should not crash if the email provider has a hiccup).
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)
    from_name = os.getenv("FROM_NAME", "ZigZag")

    subject = "Your ZigZag verification code"

    greeting = f"Hi {firstname}," if firstname else "Hi,"

    text_body = f"""{greeting}

Your verification code is: {otp}

This code expires in 15 minutes. If you didn't request this, you can safely ignore this email.

— ZigZag
"""

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
        <h2 style="margin-bottom: 8px;">Verify your email</h2>
        <p style="color: #444;">{greeting}</p>
        <p style="color: #444;">Your verification code is:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 8px; background: #f4f4f5; padding: 16px 24px; border-radius: 8px; text-align: center; margin: 16px 0;">
            {otp}
        </div>
        <p style="color: #777; font-size: 14px;">This code expires in 15 minutes. If you didn't request this, you can safely ignore this email.</p>
        <p style="color: #aaa; font-size: 12px; margin-top: 32px;">— ZigZag</p>
    </div>
    """

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_email, message.as_string())
        return True

    except Exception as e:
        # Log this properly in a real app (logging module / monitoring),
        # not just print — but never let an email failure crash the request.
        print(f"[email_service] Failed to send OTP email to {to_email}: {e}")
        return False