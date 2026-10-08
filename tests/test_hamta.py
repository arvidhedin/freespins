"""Botskyddsdetekteringen: riktiga kontroller ska märkas, vanliga sidor med skyddsskript inte."""

from bonusapp.hamta import ar_botskydd


def test_cloudflare_kontroll():
    assert ar_botskydd(403, "<title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1'>")


def test_skript_pa_vanlig_sida_ar_inget_botskydd():
    assert not ar_botskydd(200, '<div id="root"></div><script src="/_Incapsula_Resource?SWJIYLWA=1"></script>')
    assert not ar_botskydd(200, '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script><p>Casino</p>')


def test_svagt_tecken_med_403():
    assert ar_botskydd(403, "<p>Access denied</p><script src='/_Incapsula_Resource'></script>")
