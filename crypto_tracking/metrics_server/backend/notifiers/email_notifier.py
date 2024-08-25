from crypto_tracking.metrics_server.backend.alert_handler import NotifierAbs


class EmailNotifier(NotifierAbs):
    """Class for sending email notifications"""

    def __init__(self) -> None:
        raise NotImplementedError("EmailNotifier is not implemented yet")

    def send_alert(self, msg: str) -> None:
        pass
