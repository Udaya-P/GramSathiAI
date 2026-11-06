"""Conservative, deterministic claim checks; NOT a semantic entailment model.

All free-form claims retain a human-review warning even when narrow checks pass.
Recognized explicit clauses can establish a candidate amount/status relationship;
unknown languages/wording are flagged, never guessed or translated. Original
Unicode evidence is never rewritten by this module.
"""
import re
import unicodedata
from decimal import Decimal
from types import SimpleNamespace

from app import schemas


_SMALL = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
_SMALL.update(dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10))))
_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000, "crore": 10000000}
_LOCAL_NUMBERS = {"పదిహేను వేలు": 15000, "పదిహేను వేల": 15000, "పదిహేడు వేలు": 17000,
                  "ಹದಿನೈದು ಸಾವಿರ": 15000, "ಹದಿನೇಳು ಸಾವಿರ": 17000,
                  "पंद्रह हजार": 15000, "सत्रह हजार": 17000}
_NUMBER_WORD = "(?:" + "|".join([*_SMALL, *_SCALES, "and"]) + ")"
_NUMBER = rf"(?:\d[\d,]*(?:\.\d{{1,2}})?|{_NUMBER_WORD}(?:[ -]+{_NUMBER_WORD}){{0,9}}|{'|'.join(_LOCAL_NUMBERS)})"
_CURRENCIES = {"INR": r"(?:₹|\binr\b|\brs\.?|\brupees?\b|रुपये|रुपए|రూపాయలు|రూపాయల|ರೂಪಾಯಿ)",
               "USD": r"(?:\$|\busd\b|\bdollars?\b)", "EUR": r"(?:€|\beur\b|\beuros?\b)"}


def folded(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(str(unicodedata.digit(c)) if c.isdecimal() else c for c in text)


def number_value(raw):
    raw = folded(raw).strip()
    if raw in _LOCAL_NUMBERS:
        return Decimal(_LOCAL_NUMBERS[raw])
    if re.fullmatch(r"\d[\d,]*(?:\.\d+)?", raw):
        return Decimal(raw.replace(",", ""))
    total = current = 0
    for word in raw.replace("-", " ").split():
        if word in _SMALL:
            current += _SMALL[word]
        elif word == "hundred":
            current = (current or 1) * 100
        elif word in _SCALES:
            total += (current or 1) * _SCALES[word]
            current = 0
        elif word != "and":
            return None
    return Decimal(total + current)


def money_mentions(text):
    text = folded(text)
    found = set()
    for currency, symbol in _CURRENCIES.items():
        for pattern in (rf"{symbol}\s*({_NUMBER})(?!\w)", rf"(?<!\w)({_NUMBER})\s*{symbol}"):
            for match in re.finditer(pattern, text):
                amount = number_value(match.group(1))
                if amount is not None:
                    found.add((amount, currency))
    return found


def _kinds(text):
    """Explicit propositions plus negation, modality and question guards.

    Mere mentions such as 'approval', 'agreed' or 'should approve' never count.
    This intentionally recognizes only a small set of unambiguous constructions.
    """
    text = folded(text)
    kinds = set()
    uncertain = bool(re.search(r"\b(if|whether|might|may|should|would|could|suggest|suggested|hypothetical|example|false|asked|denied|quote)\b|\?", text))
    negative = bool(re.search(r"\b(not|never|hasn't|isn't|wasn't)\b.{0,20}\bapproved\b|\bunapproved\b|ఆమోదించలేదు|आम सहमति नहीं|स्वीकृत नहीं|ಅನುಮೋದಿಸಿಲ್ಲ", text))
    if negative:
        kinds.add("unapproved")
    approval = bool(re.search(r"\b(proposal|budget|allocation|motion|resolution|funding)\b.{0,65}\b(is|was|stands|has been)\s+(?:(?:formally|hereby)\s+)?approved\b|\bwe hereby (approve|adopt|sanction)\b|ప్రతిపాదన.{0,20}ఆమోదించబడింది|प्रस्ताव.{0,20}स्वीकृत किया गया|ಪ್ರಸ್ತಾವನೆ.{0,20}ಅನುಮೋದಿಸಲಾಗಿದೆ", text))
    if approval and not negative and not uncertain:
        kinds.add("approved")
    rejection = bool(re.search(r"\b(proposal|budget|allocation|motion|resolution)\b.{0,65}\b(is|was|has been)\s+(?:formally\s+)?rejected\b|\bwe hereby reject\b|ప్రతిపాదన.{0,20}తిరస్కరించబడింది|प्रस्ताव.{0,20}अस्वीकृत किया गया|ಪ್ರಸ್ತಾವನೆ.{0,20}ತಿರಸ್ಕರಿಸಲಾಗಿದೆ", text))
    if rejection and not uncertain and not re.search(r"\bnot\b.{0,15}\brejected\b", text):
        kinds.add("rejected")
    if re.search(r"\b(deferred|postponed|pending|not yet decided)\b|వాయిదా|स्थगित|ಮುಂದೂಡ", text):
        kinds.add("deferred")
    if re.search(r"\b(propose|proposed|proposal|suggest|suggested)\b|ప్రతిపాద|प्रस्ताव|ಪ್ರಸ್ತಾಪ", text):
        kinds.add("proposed")
    if re.search(r"\b(estimate|estimated|approximately|approximate|estimated cost)\b|అంచనా|अनुमान|ಅಂದಾಜು", text):
        kinds.add("estimate")
    return kinds


def _events(items):
    result = []
    for segment_id, text in items:
        # Analysis copy only. Preserve decimal points and common currency abbreviation.
        text = re.sub(r"\brs\.", "Rs", text, flags=re.I)
        for clause in re.split(r"(?<=[!?।])\s+|\.(?!\d)\s+|;|\n+", text):
            if clause.strip():
                result.append({"id": segment_id, "text": clause, "kinds": _kinds(clause), "money": money_mentions(clause)})
    return result


def _approved_bindings(events, order=None):
    bindings = set()
    for index, event in enumerate(events):
        if "approved" not in event["kinds"] or "estimate" in event["kinds"]:
            continue
        bindings.update(event["money"])
        # Resolve only a directly adjacent monetary proposal followed by explicit
        # approval. Estimates, other intervening clauses, and general agreement
        # cannot supply an approved amount. The result still requires review.
        if not event["money"] and index > 0:
            previous = events[index - 1]
            if ("proposed" in previous["kinds"] and not previous["kinds"] & {"estimate", "rejected", "unapproved", "deferred"}
                    and len(previous["money"]) == 1
                    and (order is None or previous["id"] == event["id"] or order[event["id"]] == order[previous["id"]] + 1)
                    and re.search(r"\b(the|this|that) proposal\b", folded(event["text"]))):
                bindings.update(previous["money"])
    return bindings


def _warning(code, entity, message, ids, *, fatal=False):
    return {"code": code, "entity": entity, "explanation": message,
            "evidence_segment_ids": list(dict.fromkeys(ids)), "requires_human_review": True,
            "severity": "error" if fatal else "warning", "acknowledged": False}


def claims(payload):
    summary_ids = payload.summary_evidence_segment_ids or sorted({i for c in payload.summary_claims for i in c.evidence_segment_ids})
    yield "summary", SimpleNamespace(text=payload.summary, evidence_segment_ids=summary_ids, evidence_quotes=[])
    for index, claim in enumerate(payload.summary_claims):
        yield f"summary_claims[{index}]", claim
    for collection in ("decisions", "action_items", "unresolved_issues"):
        for index, claim in enumerate(getattr(payload, collection)):
            yield f"{collection}[{index}]", claim


def evidence_ids(payload):
    return {i for _, claim in claims(payload) for i in claim.evidence_segment_ids}


def check_minutes(payload, segments, *, generated=False):
    by_id = {segment.id: segment for segment in segments}
    order = {segment.id: index for index, segment in enumerate(segments)}
    warnings = []
    all_events = _events([(s.id, s.text) for s in segments])
    all_approved = _approved_bindings(all_events, order)
    for entity, claim in claims(payload):
        ids = claim.evidence_segment_ids
        missing = sorted(set(ids) - by_id.keys())
        if missing:
            warnings.append(_warning("INVALID_EVIDENCE_REFERENCE", entity, "Citation is missing or belongs to another meeting; nothing was saved.", missing, fatal=True))
            continue
        if not ids:
            warnings.append(_warning("INSUFFICIENT_EVIDENCE", entity, "The claim has no supporting citations.", [], fatal=generated or entity != "summary"))
            continue
        invalid_quote = False
        for quote in claim.evidence_quotes:
            if quote.segment_id not in ids or quote.quote not in by_id[quote.segment_id].text:
                warnings.append(_warning("INSUFFICIENT_EVIDENCE", entity, "An evidence quote is not an exact excerpt of a cited segment.", [quote.segment_id], fatal=True))
                invalid_quote = True
        if invalid_quote:
            continue
        # Quotes narrow a claim's scope. IDs without quotes use the full source,
        # but approval/amount relationships must still pass the checks below.
        selected = [(i, by_id[i].text) for i in sorted(set(ids), key=order.get)]
        full_events = _events(selected)
        full_kinds = set().union(*(e["kinds"] for e in full_events)) if full_events else set()
        if claim.evidence_quotes:
            selected = [(q.segment_id, q.quote) for q in sorted(
                claim.evidence_quotes, key=lambda q: (order[q.segment_id], by_id[q.segment_id].text.index(q.quote)))]
        events = _events(selected)
        kinds = set().union(*(e["kinds"] for e in events)) if events else set()
        # A true excerpt can still omit 'if', a question mark or surrounding
        # negation. Neither status nor money bindings may exceed full context.
        for status in ("approved", "rejected"):
            if status not in full_kinds:
                kinds.discard(status)
        kinds.update(full_kinds & {"unapproved", "rejected", "deferred"})
        text = "\n".join(t for _, t in selected)
        warnings.append(_warning("CLAIM_SUPPORT_UNVERIFIED", entity, "Valid citations and narrow deterministic checks do not prove the full meaning of this claim. Review the original evidence.", ids))
        description = getattr(claim, "description", getattr(claim, "task", getattr(claim, "text", "")))
        unsupported_numbers = money_mentions(description) - money_mentions(text)
        if unsupported_numbers:
            warnings.append(_warning("UNSUPPORTED_BUDGET", entity, "A monetary claim in the prose is absent from its cited evidence.", ids))
        prose_kinds = _kinds(description)
        if "approved" in prose_kinds and "approved" not in kinds:
            warnings.append(_warning("UNSUPPORTED_APPROVAL", entity, "The claim prose asserts approval that the evidence does not establish.", ids))
        if "approved" in prose_kinds and money_mentions(description) - (_approved_bindings(events, order) & _approved_bindings(full_events, order)):
            warnings.append(_warning("UNSUPPORTED_BUDGET", entity, "The prose treats a discussed monetary amount as approved without an appropriate approval link.", ids))
        if isinstance(claim, schemas.DecisionCreate):
            classification = claim.classification
            if classification == "approved" and "approved" not in kinds:
                warnings.append(_warning("UNSUPPORTED_APPROVAL", entity, "No explicit, non-negated formal approval proposition was recognized. A proposal or agreement is not approval.", ids))
            if classification == "rejected" and "rejected" not in kinds:
                warnings.append(_warning("UNSUPPORTED_REJECTION", entity, "No explicit rejection was recognized. Not approved does not necessarily mean rejected.", ids))
            if (classification in {"unclear", "deferred"} or kinds >= {"approved", "rejected"}
                    or (classification == "approved" and kinds & {"unapproved", "rejected", "deferred"})
                    or (classification in {"proposed", "rejected"} and "approved" in kinds)):
                warnings.append(_warning("AMBIGUOUS_DECISION_STATUS", entity, "The classification is uncertain or conflicts with the cited status statements.", ids))
            approved = _approved_bindings(events, order) & _approved_bindings(full_events, order)
            target = (claim.approved_amount if claim.approved_amount is not None else claim.proposed_amount, claim.currency)
            contradictory = [e for e in all_events if target in e["money"] and e["kinds"] & {"rejected", "unapproved"}]
            if (classification == "approved" and contradictory
                    or classification == "proposed" and claim.proposed_amount is not None and target in all_approved):
                context_ids = [e["id"] for e in contradictory] or list(ids)
                warnings.append(_warning("AMBIGUOUS_DECISION_STATUS", entity, "Other persisted meeting evidence conflicts with this budget classification. Review the whole discussion.", [*ids, *context_ids]))
            for field, role in (("estimated_amount", "estimate"), ("proposed_amount", "proposed"), ("approved_amount", "approved")):
                amount = getattr(claim, field)
                if amount is None:
                    continue
                pair = (amount, claim.currency)
                if role == "approved":
                    supported = pair in approved and classification == "approved"
                else:
                    supported = any(pair in e["money"] and role in e["kinds"] for e in events)
                if not supported:
                    warnings.append(_warning("UNSUPPORTED_BUDGET", f"{entity}.{field}", "The cited text does not establish this amount AND currency in its claimed role (estimate, proposal or approved allocation).", ids))
                if role == "approved" and (approved and pair not in approved or classification != "approved"
                        or pair not in approved and any(pair in e["money"] and "estimate" in e["kinds"] for e in events)):
                    warnings.append(_warning("CONFLICTING_AMOUNTS", f"{entity}.{field}", "An estimate, unapproved amount or different approved allocation is being represented as approved.", ids))
        if isinstance(claim, schemas.ActionCreate):
            _check_action(claim, entity, full_events, ids, warnings)
        if entity.startswith("summary"):
            for literal in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", description):
                if literal not in text:
                    warnings.append(_warning("INSUFFICIENT_EVIDENCE", entity, "A calendar date in the summary is not present in the cited text.", ids))
    # Conflicts across candidate decisions sharing evidence are reviewable, not
    # silently resolved. Distinct projects can legitimately have different sums.
    for i, first in enumerate(payload.decisions):
        for j in range(i + 1, len(payload.decisions)):
            second = payload.decisions[j]
            shared = sorted(set(first.evidence_segment_ids) & set(second.evidence_segment_ids))
            if not shared:
                continue
            if (first.approved_amount is not None and second.approved_amount is not None
                    and (first.approved_amount, first.currency) != (second.approved_amount, second.currency)):
                warnings.append(_warning("CONFLICTING_AMOUNTS", f"decisions[{i}],decisions[{j}]", "Decisions sharing evidence assert different approved amounts; check whether they describe the same allocation.", shared))
            if {first.classification, second.classification} >= {"approved", "rejected"}:
                warnings.append(_warning("AMBIGUOUS_DECISION_STATUS", f"decisions[{i}],decisions[{j}]", "Decisions sharing evidence assert contradictory approval/rejection states.", shared))
    return warnings


def _check_action(claim, entity, events, ids, warnings):
    if claim.assigned_to is None:
        warnings.append(_warning("INSUFFICIENT_EVIDENCE", f"{entity}.assigned_to", "Assignee remains unknown; do not invent one.", ids))
    else:
        assignee = folded(claim.assigned_to)
        # Mentioning a person is insufficient: require a commitment/assignment
        # in the same clause, with the assignee preceding the assignment verb.
        pattern = re.escape(assignee) + r"\s+(?:(?:has been|is)\s+assigned to|will|must|shall|is responsible for|must coordinate)\b"
        terms = {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", folded(claim.task))} - {"provide", "within", "days", "that", "this", "with", "from"}
        assigned = any(re.search(pattern, folded(e["text"]))
                       and not re.search(r"\b(may|might|should|could|not|if)\b|\?", folded(e["text"]))
                       and terms and len(terms & {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", folded(e["text"]))}) >= min(2, len(terms))
                       for e in events)
        if not assigned:
            warnings.append(_warning("UNSUPPORTED_ASSIGNEE", entity, "No unambiguous assignment to this assignee was recognized in the cited clause; a mention or suggestion is insufficient.", ids))
    date_events = [e for e in events if claim.deadline and claim.deadline.isoformat() in e["text"]]
    task_is_progress = bool(re.search(r"\b(progress|update|report)\b", folded(claim.task)))
    calendar_supported = any(re.search(r"\b(must|shall|will|required|due|deadline)\b", folded(e["text"]))
                             and not re.search(r"\b(suggest|suggested|may|might|should|could|propose|proposed|if)\b|\?", folded(e["text"]))
                             and (task_is_progress or not re.search(r"\b(progress|update|report)\b", folded(e["text"])))
                             for e in date_events)
    if claim.deadline and not calendar_supported:
        warnings.append(_warning("UNSUPPORTED_DEADLINE", entity, "The calendar date is not explicit in the evidence. No relative phrase is converted to a date using an unverified meeting-date anchor.", ids))
    if claim.deadline_text:
        deadline = " ".join(folded(claim.deadline_text).split())
        matching = [e for e in events if deadline in " ".join(folded(e["text"]).split())]
        suggestion = any(re.search(r"\b(suggest|suggested|may|might|should|could|propose|proposed|if)\b|\?", folded(e["text"])) for e in matching)
        progress = any(re.search(r"\b(progress|update|report)\b", folded(e["text"])) for e in matching)
        committed = any(re.search(r"\b(must|shall|will|required)\b", folded(e["text"])) for e in matching)
        if not matching or suggestion or not committed or progress and not task_is_progress:
            warnings.append(_warning("UNSUPPORTED_DEADLINE", entity, "Deadline wording is absent, suggested rather than committed, or applies to a progress update rather than the claimed task.", ids))
