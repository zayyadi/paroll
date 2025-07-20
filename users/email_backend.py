from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


class EmailBackend(SMTPEmailBackend):
    def send_messages(self, email_messages):
        for email_message in email_messages:
            if email_message.template_name:
                html_content = render_to_string(
                    email_message.template_name, email_message.context
                )
                text_content = strip_tags(html_content)
                email_message.body = text_content
                email_message.content_subtype = "html"  # Set content type to HTML
                email_message.alternatives = [(html_content, "text/html")]
        return super().send_messages(email_messages)


def send_mail(
    subject,
    template_name,
    context,
    from_email,
    recipient_list,
    fail_silently=False,
    attachments=None,
):
    from django.core.mail import EmailMessage

    email_message = EmailMessage(
        subject=subject,
        body="",  # Body will be rendered from template
        from_email=from_email,
        to=recipient_list,
    )
    email_message.template_name = template_name
    email_message.context = context

    if attachments:
        for attachment in attachments:
            filename = attachment.get("filename")
            content = attachment.get("content")
            mimetype = attachment.get("mimetype")
            email_message.attach(filename, content, mimetype)

    return email_message.send(fail_silently=fail_silently)
