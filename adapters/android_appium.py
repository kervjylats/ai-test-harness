"""
adapters/android_appium.py

Drives a Flutter (or Expo/React Native — Appium doesn't care) app on an
Android emulator via Appium's UiAutomator2 driver.

⚠️ STATUS: scaffolded, not verified — I have no Android emulator or Appium
server available in the sandbox this was written in. Structurally this
follows Appium's standard Python-client pattern correctly, but budget a
first real run to iron out capability details for your specific setup
(emulator name, app path) before trusting it unattended.

One-time setup on YOUR machine:
    npm install -g appium
    appium driver install uiautomator2
    pip install Appium-Python-Client
    appium                      # starts the Appium server, leave running
    # separately: have your Android emulator already running
    #   (Android Studio > Device Manager > launch one), or
    #   `emulator -avd <your_avd_name>` from the command line

Project config keys this adapter reads:
    "apk_path":     path to a debug APK
                    (flutter build apk --debug, or Expo's local dev build)
    "app_package":  Android package name, e.g. "com.yourcompany.app"
    "app_activity": usually ".MainActivity" — check your
                    android/app/src/main/AndroidManifest.xml if unsure
    "device_name":  whatever your emulator calls itself in
                    `adb devices` (e.g. "emulator-5554")
    "appium_url":   defaults to http://localhost:4723 if omitted
"""

from pathlib import Path

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

from .base import Adapter


class AndroidAppiumAdapter(Adapter):
    def __init__(self):
        self._driver = None

    def launch(self, config: dict) -> None:
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.device_name = config.get("device_name", "emulator-5554")
        options.app = config["apk_path"]
        options.app_package = config["app_package"]
        options.app_activity = config["app_activity"]
        # Flutter/RN apps need a beat after install+launch before the
        # widget tree is fully up — tune this if your app is heavier.
        options.new_command_timeout = 120

        appium_url = config.get("appium_url", "http://localhost:4723")
        self._driver = webdriver.Remote(appium_url, options=options)

    def screenshot(self, out_path: Path) -> Path:
        self._driver.get_screenshot_as_file(str(out_path))
        return out_path

    def find_text(self, text: str) -> dict | None:
        # UiAutomator2's textContains() reads Android's accessibility
        # tree — Flutter populates this automatically once an
        # accessibility service (which Appium counts as) is attached, so
        # this should "just work" the same way TalkBack would see the app.
        try:
            el = self._driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().textContains("{text}")',
            )
        except Exception:
            return None
        rect = el.rect  # {'x', 'y', 'width', 'height'}
        return {
            "x": int(rect["x"] + rect["width"] / 2),
            "y": int(rect["y"] + rect["height"] / 2),
            "matched": text,
        }

    def tap(self, x: int, y: int) -> None:
        self._driver.execute_script("mobile: clickGesture", {"x": x, "y": y})

    def type_text(self, text: str) -> None:
        # Requires a field to already have focus (tap it first via
        # find_text + tap, same as every other adapter's convention).
        active = self._driver.switch_to.active_element
        active.send_keys(text)

    def close(self) -> None:
        if self._driver:
            self._driver.quit()
