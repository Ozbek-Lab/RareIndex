from django.tasks import task
from django.core.mail import EmailMessage


@task
def send_notification_email(subject, message, recipient_list):
    """Send a notification email. Uses fail_silently so a broken SMTP
    configuration never crashes a task or a management command."""
    email = EmailMessage(subject, message, to=recipient_list)
    email.send(fail_silently=True)
