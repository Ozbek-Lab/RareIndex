from django.tasks import task
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


def _valid_ascii_email(address):
    address = str(address or "").strip()
    if not address or not address.isascii():
        return False
    try:
        validate_email(address)
    except ValidationError:
        return False
    return True


@task
def send_notification_email(subject, message, recipient_list):
    """Send a notification email. Uses fail_silently so a broken SMTP
    configuration never crashes a task or a management command."""
    recipients = [address for address in recipient_list if _valid_ascii_email(address)]
    if not recipients:
        return 0
    try:
        email = EmailMessage(subject, message, to=recipients)
        return email.send(fail_silently=True)
    except ValueError:
        return 0
