"""probe_switches.py - dump the Availability card switch DOM.

Round 7 follow-up: the harness resolved switches by POSITION
(card_titles[i] -> flt-semantics[role=switch][i]). Adding the
'Visible to owners with the same job' row shifted that alignment and
toggle_slot silently clicked the WRONG switch (turn 11 FAIL).

This probe prints, for every switch on the marketplace page:
  index, own aria-label, aria-checked, nearest labelled ancestor
so the harness can switch to label-based lookup.
"""
import json

from playwright.sync_api import sync_playwright

import master_test as mt
from server_control import BASE, ensure_server, stop_server

OWNER = dict(name="Probe", email="probe@robot.test",
             category="Movement & Fitness", job="Yoga Studio",
             business="Probe Yoga Co", tagline="probe biz")

DUMP = """() => {
  const resolve = (s => {
    let label = (s.getAttribute('aria-label') || '').trim();
    if (label) return label;
    let n = s;
    for (let d = 0; d < 6 && n; d++) {
      n = n.parentElement;
      if (!n || !n.getAttribute) continue;
      const a = (n.getAttribute('aria-label') || '').trim();
      if (a && !a.includes('My Availability')) return a.split('\\n')[0].trim();
    }
    return '';
  });
  return Array.from(document.querySelectorAll(
      'flt-semantics[role=switch]')).map((s, i) => ({
    i,
    own: (s.getAttribute('aria-label') || '').slice(0, 50),
    label: resolve(s).slice(0, 50),
    checked: s.getAttribute('aria-checked') || '',
    disabled: s.getAttribute('aria-disabled') === 'true',
  }));
}"""


def main():
    if not ensure_server():
        print("server failed")
        return 1
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(9000)
            url = mt.signup(page, OWNER["name"], OWNER["email"],
                            OWNER["category"], OWNER["job"], OWNER["business"],
                            tagline=OWNER["tagline"], password="demo123")
            print("signup:", url)
            mt.go_marketplace(page)
            page.wait_for_timeout(4000)
            mt.enable_flutter_acc(page)
            mt.scroll_down(page, steps=5)
            page.wait_for_timeout(2500)
            data = page.evaluate(DUMP)
            print(json.dumps(data, indent=2))
            print("\ncard_titles ->", mt.card_titles(page))
            print("switch_states ->", mt.switch_states(page))

            print("\n--- label-based toggles (expect: OK / OK / locked / OK / OK)")
            print("Discoverable ->", mt.toggle_slot(page, "Discoverable"))
            print("Pilates Studio ->", mt.toggle_slot(page, "Pilates Studio"))
            print("Yoga Studio (own trade, same-job OFF) ->",
                  mt.toggle_slot(page, "Yoga Studio"))
            print("same-job ->",
                  mt.toggle_slot(page, "Visible to owners with the same job"))
            print("Yoga Studio retry ->", mt.toggle_slot(page, "Yoga Studio"))
            print("first 4 switches ->", json.dumps(mt.switch_map(page)[:4]))
            browser.close()
    finally:
        stop_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
