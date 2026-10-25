# ruff: noqa: E501
"""Audit-only real Chromium browser walk-through and negative interaction tests."""
import json
import re

from playwright.sync_api import expect, sync_playwright


def run():
    issues = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda error: issues.append(f"Browser JavaScript exception: {error}"))
        page.goto("http://127.0.0.1:8080/", wait_until="domcontentloaded")
        expect(page.locator("#map")).to_be_visible()
        page.wait_for_function("typeof window.L !== 'undefined'", timeout=30000)
        page.locator("#area-name").fill("Maroochydore Chromium Audit")
        page.locator("#btn-create-project").click()
        expect(page.locator("#project-status")).to_contain_text("Active Project:", timeout=30000)
        page.locator("#btn-preset-mcy").click()
        expect(page.locator("#btn-save-revision")).to_be_enabled(timeout=30000)
        page.locator("#btn-save-revision").click()
        expect(page.locator("#btn-submit-job")).to_be_enabled(timeout=30000)
        print("PASS: real browser project creation, geometry, viability and save",flush=True)

        # Deliberately change the current geofence after saving. It should invalidate the old revision.
        page.locator("#btn-clear-poly").click()
        if page.locator("#btn-submit-job").is_enabled():
            issues.append("STALE_GEOFENCE: submit job remains enabled after clearing a saved polygon")
        page.locator("#btn-preset-mcy").click()
        expect(page.locator("#btn-save-revision")).to_be_enabled(timeout=30000)
        page.locator("#btn-save-revision").click()
        expect(page.locator("#btn-submit-job")).to_be_enabled(timeout=30000)
        page.locator("#btn-submit-job").click()
        expect(page.locator("#job-status-readout")).to_contain_text("created",timeout=30000)
        page.locator("#btn-run-job").click()
        expect(page.locator("#job-status-readout")).to_contain_text("proof_ready",timeout=120000)
        expect(page.locator("#artifact-links .artifact-btn")).to_have_count(5)
        page.locator("#artifact-links button[data-artifact='qa-report.json']").click()
        expect(page.locator("#qa-preview")).to_contain_text('"passed": true',timeout=20000)
        print("PASS: actual Chromium render-to-QA workflow",flush=True)

        # Reflect a deliberately hostile server error payload in the existing job status UI.
        job_line = page.locator("#job-status-readout").inner_text()
        m = re.search(r"Job ID:\s*([^\s]+)", job_line)
        assert m,job_line
        jid = m.group(1)
        def intercept(route):
            response = route.fetch()
            d = response.json()
            d["error_code"] = "INJECT"
            d["error_detail"] = '<img src=x onerror="window.__maps4u_xss=1">'
            route.fulfill(status=200, content_type="application/json", body=json.dumps(d))
        target = "**/api/jobs/" + jid
        page.route(target,intercept)
        page.locator("#btn-refresh-job").click()
        page.wait_for_timeout(1000)
        if page.evaluate("window.__maps4u_xss === 1"):
            issues.append("DOM_XSS: attacker-controlled API error_detail executes code in job-status-readout")
        page.unroute(target,intercept)
        page.locator("#btn-refresh-job").click()
        expect(page.locator("#btn-approve-job")).to_be_enabled(timeout=30000)
        page.locator("#btn-approve-job").click()
        expect(page.locator("#job-status-readout")).to_contain_text("finalized",timeout=30000)
        page.screenshot(path="/tmp/maps4u-browser-audit.png", full_page=True)
        print("PASS: browser proof approval and finalised status",flush=True)
        browser.close()
    for issue in issues:
        print("FINDING:", issue, flush=True)
    assert not issues, f"Browser regressions: {issues}"
    print("PASS: no browser safety/correctness regressions",flush=True)

if __name__ == "__main__":
    run()
