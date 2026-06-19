import importlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def test_get_logger_uses_rotating_file_and_warning_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GARMIN_LOG_PATH", str(tmp_path / "logs" / "bot.log"))

    import analytics.common as common

    common = importlib.reload(common)
    logger = logging.getLogger("test_logger_config")
    logger.handlers.clear()

    configured = common.get_logger("test_logger_config")

    file_handlers = [h for h in configured.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == 5 * 1024 * 1024
    assert file_handlers[0].backupCount == 3
    assert file_handlers[0].baseFilename.endswith("logs/bot.log")

    stream_handlers = [
        h
        for h in configured.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
    ]
    assert len(stream_handlers) == 1
    assert stream_handlers[0].level == logging.WARNING

    configured.warning("visible warning")
    for handler in configured.handlers:
        handler.flush()

    assert "visible warning" in Path(file_handlers[0].baseFilename).read_text()
    assert "visible warning" in capsys.readouterr().err
