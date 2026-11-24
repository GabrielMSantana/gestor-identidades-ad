import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config.settings import ConfigEmail


class SMTPClient:
    def __init__(self, config: ConfigEmail):
        self.email_user = config.usuario
        self.email_pass = config.senha
        self.email_dest = config.destinatarios
        self.email_cc = config.copia
        self.host = config.smtp_host
        self.port = config.smtp_porta

    def enviar_email(self, assunto, mensagem, anexo=None, cc=None, bcc=None):
        # Junta o CC do .env com o recebido na chamada
        cc_list = self._formatar_lista(self.email_cc) + self._formatar_lista(cc)
        bcc_list = self._formatar_lista(bcc)
        to_list = self._formatar_lista(self.email_dest)

        # Monta a lista final de envio
        destinatarios = to_list + cc_list + bcc_list

        # Construtor do e-mail
        email_msg = MIMEMultipart()
        email_msg["From"] = self.email_user
        email_msg["To"] = ", ".join(to_list)

        if cc_list:
            email_msg["Cc"] = ", ".join(cc_list)

        email_msg["Subject"] = assunto
        email_msg.attach(MIMEText(mensagem, "html"))

        # Anexar arquivo
        if anexo:
            with open(anexo, "rb") as f:
                file = MIMEApplication(f.read())
                file.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=os.path.basename(anexo)
                )
                email_msg.attach(file)

        # Envio
        context = ssl.create_default_context()
        with smtplib.SMTP(self.host, self.port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(self.email_user, self.email_pass)
            server.sendmail(self.email_user, destinatarios, email_msg.as_string())

    def _formatar_lista(self, item):
        """Aceita string, lista ou None e devolve sempre uma lista limpa."""
        if item is None:
            return []

        if isinstance(item, str):
            return [i.strip() for i in item.split(",") if i.strip()]

        if isinstance(item, list):
            return [i.strip() for i in item if i.strip()]

        return []
