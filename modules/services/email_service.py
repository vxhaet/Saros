"""Service d'envoi d'emails (brique verte).

Interchangeable : on peut passer de SMTP à SendGrid ou autre
en modifiant uniquement ce fichier.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..anonymisation.config import settings


def send_approval_email(
    admin_email: str,
    admin_name: str,
    requester_name: str,
    requester_email: str,
    group_name: str,
    approval_url: str,
    reject_url: str,
) -> bool:
    """Envoie un email de demande d'approbation à un admin de groupe.

    Retourne True si l'envoi a réussi, False sinon.
    """
    if not settings.smtp_host:
        print(
            f"[EMAIL] SMTP non configuré. Approbation en attente pour "
            f"{requester_email} → groupe '{group_name}'. "
            f"Approuver : {approval_url}"
        )
        return False

    subject = f"Saros — Demande d'accès au groupe '{group_name}'"

    html = f"""\
    <html>
    <body>
        <h2>Nouvelle demande d'accès</h2>
        <p><strong>{requester_name}</strong> ({requester_email}) souhaite
        rejoindre le groupe <strong>{group_name}</strong>.</p>
        <p>
            <a href="{approval_url}"
               style="background:#28a745;color:white;padding:10px 20px;
                      text-decoration:none;border-radius:5px;">
                Approuver
            </a>
            &nbsp;&nbsp;
            <a href="{reject_url}"
               style="background:#dc3545;color:white;padding:10px 20px;
                      text-decoration:none;border-radius:5px;">
                Refuser
            </a>
        </p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = admin_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], admin_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Erreur d'envoi à {admin_email}: {e}")
        return False
