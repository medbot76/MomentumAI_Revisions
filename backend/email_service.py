import os
import requests

SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
FROM_EMAIL = 'ebad.khan5487@gmail.com'
FROM_NAME = 'Momentum AI'

LOGO_URL = os.environ.get('REPLIT_DEV_DOMAIN', '')
if LOGO_URL:
    LOGO_URL = f"https://{LOGO_URL}/medbotlogonew.jpg"


def send_verification_email(to_email: str, verification_code: str, first_name: str = '') -> bool:
    """Send email verification code via SendGrid"""
    if not SENDGRID_API_KEY:
        print("Warning: SENDGRID_API_KEY not set, skipping email send")
        return False
    
    greeting = f"Hi {first_name}," if first_name else "Hi there,"
    
    logo_html = ""
    if LOGO_URL:
        logo_html = f'''
                <div style="text-align: center; margin-bottom: 24px;">
                    <img src="{LOGO_URL}" alt="Momentum AI" style="width: 80px; height: 80px; border-radius: 12px;">
                </div>'''
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background-color: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                {logo_html}
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #1a1a1a; font-size: 24px; margin: 0;">Verify Your Email</h1>
                </div>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6; margin-bottom: 20px;">
                    {greeting}
                </p>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                    Thank you for signing up for Momentum AI! Please use the verification code below to complete your registration:
                </p>
                
                <div style="background-color: #f8f9fa; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 30px;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1a1a1a;">{verification_code}</span>
                </div>
                
                <p style="color: #666; font-size: 14px; line-height: 1.6; margin-bottom: 20px;">
                    This code will expire in 15 minutes. If you didn't create an account with Momentum AI, you can safely ignore this email.
                </p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="color: #999; font-size: 12px; text-align: center; margin: 0;">
                    Momentum AI - Your AI Study Assistant
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""{greeting}

Thank you for signing up for Momentum AI! Please use the verification code below to complete your registration:

{verification_code}

This code will expire in 15 minutes. If you didn't create an account with Momentum AI, you can safely ignore this email.

- Momentum AI Team
"""
    
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": f"Your Momentum AI verification code: {verification_code}",
        "content": [
            {"type": "text/plain", "value": text_content},
            {"type": "text/html", "value": html_content}
        ]
    }
    
    try:
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )
        
        if response.status_code in [200, 201, 202]:
            print(f"Verification email sent successfully to {to_email}")
            return True
        else:
            print(f"Failed to send email: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
