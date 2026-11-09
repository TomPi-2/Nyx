r"""Settings: ajustes en %APPDATA%\Nyx\settings.json con esquema versionado y migraciones."""

from nyx.settings.model import Settings, load_settings, save_settings, settings_path

__all__ = ["Settings", "load_settings", "save_settings", "settings_path"]
