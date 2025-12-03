from django.tasks import task
from django.core.mail import EmailMessage


@task
def send_notification_email(subject, message, recipient_list):
    """
    Background task to send notification emails using Django 6 tasks.
    """
    email = EmailMessage(subject, message, to=recipient_list)
    email.send()
