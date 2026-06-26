import importlib.util, pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("frf", SCRIPTS / "fetch_reference_figures.py")
frf = importlib.util.module_from_spec(spec); spec.loader.exec_module(frf)


def test_venue_tier():
    assert frf.venue_tier("IEEE Transactions on Geoscience and Remote Sensing") == 1
    assert frf.venue_tier("Remote Sensing") == 2          # MDPI mid
    assert frf.venue_tier("Some Random Workshop") == 3


def test_arxiv_id_from_url():
    assert frf.arxiv_id("https://arxiv.org/abs/2103.00208") == "2103.00208"
    assert frf.arxiv_id("https://arxiv.org/abs/1810.08462v2") == "1810.08462"
    assert frf.arxiv_id("https://www.mdpi.com/2072-4292/12/10/1662") is None


def test_ar5iv_html_url():
    assert frf.ar5iv_url("2103.00208") == "https://ar5iv.labs.arxiv.org/html/2103.00208"


def test_rank_prefers_top_venue_then_order():
    papers = [
        {"title": "B", "venue": "Remote Sensing", "url": "https://arxiv.org/abs/2000.00002"},
        {"title": "A", "venue": "IEEE Transactions on Geoscience and Remote Sensing",
         "url": "https://arxiv.org/abs/2000.00001"},
    ]
    ranked = frf.rank_candidates(papers)
    assert ranked[0]["title"] == "A"   # tier-1 beats tier-2 despite later order


def test_is_main_figure_caption():
    assert frf.is_main_figure("Overall framework of the proposed BIT model.")
    assert frf.is_main_figure("The architecture of our network.")
    assert not frf.is_main_figure("Quantitative results on the test set.")
    assert not frf.is_main_figure("Training accuracy curves.")
    assert not frf.is_main_figure("Effective Receptive Field (ERF) visualized for both architectures.")


def test_main_graceful_on_missing_papers(tmp_path):
    import subprocess, sys, json as _j
    r = subprocess.run([sys.executable, str(SCRIPTS / "fetch_reference_figures.py"),
                        "--papers", str(tmp_path / "nope.json"),
                        "--out-dir", str(tmp_path / "refs"), "--label", "architecture"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = _j.loads(r.stdout.strip().splitlines()[-1])
    assert out["ok"] is True and out["n"] == 0   # degrade gracefully, do not crash
