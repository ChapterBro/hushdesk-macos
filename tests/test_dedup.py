import pytest

from hushdesk.pdf.mar_grid_extract import Evidence


def _merge(ev_list):
    # simulate precedence logic: DC'D > allowed > given->(miss/ok) > other > empty
    def decide(ev):
        if ev.text_x or ev.vec_x:
            return "DC'D"
        if ev.allowed_code is not None:
            return "HELD-APPROPRIATE"
        if ev.given_time or ev.checkmark:
            if ev.sbp and ev.sbp > 160:
                return "HOLD-MISS"
            return "COMPLIANT"
        if ev.other_code is not None:
            return "OTHER-CODE"
        return "EMPTY"

    final = Evidence()
    for ev in ev_list:
        final.text_x |= ev.text_x
        final.vec_x |= ev.vec_x
        final.checkmark |= ev.checkmark
        final.given_time = final.given_time or ev.given_time
        final.allowed_code = final.allowed_code or ev.allowed_code
        final.other_code = final.other_code or ev.other_code
        final.sbp = final.sbp if final.sbp is not None else ev.sbp
        final.hr = final.hr if final.hr is not None else ev.hr
    return decide(final)


def test_dedup_merges_text_and_vector_x():
    e1 = Evidence(text_x=True)
    e2 = Evidence(vec_x=True)
    assert _merge([e1, e2]) == "DC'D"


def test_dedup_given_vs_allowed_code():
    e1 = Evidence(checkmark=True, given_time="08:00")
    e2 = Evidence(allowed_code=11)
    assert _merge([e1, e2]) == "HELD-APPROPRIATE"


def test_dedup_given_with_sbp_trigger():
    e = Evidence(checkmark=True, sbp=165)
    assert _merge([e]) == "HOLD-MISS"
