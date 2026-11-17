# OWNER: M1
import pytest

from tests.helpers import make_ctx


def test_put_get_has_names(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.store.put("phase1_step1_scope", {"is_digital": True}, "# Scope", agent="scope_classifier", sources=["u"])
    assert ctx.store.has("phase1_step1_scope")
    assert ctx.store.get("phase1_step1_scope") == {"is_digital": True}
    assert (ctx.out_dir / "phase1_step1_scope.md").read_text() == "# Scope"
    assert ctx.store.names() == ["phase1_step1_scope"]


def test_put_overwrites(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.store.put("s", {"v": 1}, "a", agent="x")
    ctx.store.put("s", {"v": 2}, "b", agent="x")
    assert ctx.store.get("s") == {"v": 2}


def test_get_missing_raises_keyerror(tmp_path):
    with pytest.raises(KeyError):
        make_ctx(tmp_path).store.get("nope")


def test_put_file_text_formats_only(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.store.put_file("phase2_step4_landing_page", "html", "<p>MOCKED</p>", agent="x")
    assert (ctx.out_dir / "phase2_step4_landing_page.html").exists()
    with pytest.raises(ValueError):
        ctx.store.put_file("x", "png", "", agent="x")
