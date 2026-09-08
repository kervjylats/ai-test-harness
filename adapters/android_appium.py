"""
adapters/android_appium.py

Drives a Flutter (or Expo/React Native — Appium doesn't care) app on an
Android emulator via Appium's UiAutomator2 driver.

Flutter on Android renders text to a canvas and exposes it via the
accessibility tree as `content-desc` (content description), NOT as the
`text` attribute.  This adapter searches `content-desc` first, then
falls back to `text` and `hint` for native widgets.

One-time setup on YOUR machine:
    npm install -g appium
    appium driver install uiautomator2
    pip install Appium-Python-Client
    appium                      # starts the Appium server, leave running
    # separately: have your Android emulator already running

Project config keys this adapter reads:
    "apk_path":     path to a debug APK
    "app_package":  Android package name, e.g. "com.yourcompany.app"
    "app_activity": usually ".MainActivity"
    "device_name":  whatever your emulator calls itself in `adb devices`
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
        options.new_command_timeout = 120

        appium_url = config.get("appium_url", "http://localhost:4723")
        self._driver = webdriver.Remote(appium_url, options=options)

    def screenshot(self, out_path: Path) -> Path:
        self._driver.get_screenshot_as_file(str(out_path))
        return out_path

    def find_text(self, text: str) -> dict | None:
        """Search for `text` on screen.  Flutter on Android puts visible
        text into `content-desc`, so we try three selectors in order:
          1. descriptionContains  (Flutter's content-desc)
          2. textContains         (native widgets)
          3. text (exact)         (fallback)
        """
        selectors = [
            f'new UiSelector().descriptionContains("{text}")',
            f'new UiSelector().textContains("{text}")',
            f'new UiSelector().text("{text}")',
        ]
        for sel in selectors:
            try:
                el = self._driver.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR, sel
                )
                rect = el.rect
                return {
                    "x": int(rect["x"] + rect["width"] / 2),
                    "y": int(rect["y"] + rect["height"] / 2),
                    "matched": text,
                }
            except Exception:
                continue
        return None

    def find_in_region(self, text: str, region: dict) -> dict | None:
        """Find `text` only within a bounding box.
        region = {"x1", "y1", "x2", "y2"}
        Returns match dict or None."""
        selectors = [
            f'new UiSelector().descriptionContains("{text}")',
            f'new UiSelector().textContains("{text}")',
            f'new UiSelector().text("{text}")',
        ]
        for sel in selectors:
            try:
                els = self._driver.find_elements(
                    AppiumBy.ANDROID_UIAUTOMATOR, sel
                )
                for el in els:
                    r = el.rect
                    cx = r["x"] + r["width"] / 2
                    cy = r["y"] + r["height"] / 2
                    if (region["x1"] <= cx <= region["x2"] and
                            region["y1"] <= cy <= region["y2"]):
                        return {
                            "x": int(cx), "y": int(cy),
                            "matched": text,
                        }
            except Exception:
                continue
        return None

    def tap_in_region(self, text: str, region: dict) -> dict | None:
        """Find `text` in region and tap it. Returns match or None."""
        result = self.find_in_region(text, region)
        if result:
            self.tap(result["x"], result["y"])
        return result

    def tap(self, x: int, y: int) -> None:
        self._driver.execute_script("mobile: clickGesture", {"x": x, "y": y})

    def type_text(self, text: str) -> None:
        active = self._driver.switch_to.active_element
        active.send_keys(text)

    def close(self) -> None:
        if self._driver:
            self._driver.quit()
