# cpu_stack_test.py — CPU proxy for the ARC-3 stack (GH Actions + Kaggle CPU).
# NOT the full harness (no ARC-3 env here): a prompt-level A/B over stall vignettes.
# Arms: off (base prompt) vs on (base + H1 ratio line + playbook tail).
# Emits unified per-turn lines: t=.. mech=.. fire=.. next_action=.. level=..
# plus emission probe (--emit-check): RULE shape + SUPPORT resolvability.
import argparse, json, sys

def load_llm(model):
    from llama_cpp import Llama
    return Llama(model_path=model, n_ctx=2048, n_threads=8, verbose=False)

STALL_VIGNETTES = [
    (5, 180, 34, 40), (7, 150, 30, 30), (3, 90, 22, 25),
    (8, 200, 40, 50), (2, 60, 18, 20),
]

def h1_line(level, used, par):
    return ("Human par for level %d: %d actions. You have used %d (%.0f%% of par) with budget left. "
            "Quitting now repeats the observed failure. With no progress, SWITCH APPROACH, do not abandon. "
            "give_up requires an approach-switch first. Past 4x par with no progress, abandon."
            % (level, par, used, 100.0 * used / par))

def run_arm(llm, arm, turns, out_f):
    fires = {"h1": 0, "give_up": 0, "switch": 0}
    for i in range(turns):
        level, used, par, stale = STALL_VIGNETTES[i % len(STALL_VIGNETTES)]
        base = ("You used %d actions on level %d (human par %d), no score increase in %d actions. "
                "Reply one line: CONTINUE or GIVE_UP, then one sentence." % (used, level, par, stale))
        prompt = base + (" " + h1_line(level, used, par) if arm == "on" else "")
        if arm == "on":
            fires["h1"] += 1
        r = llm.create_chat_completion(
            messages=[{"role": "system", "content": "Reply with one line: CONTINUE or GIVE_UP, then one sentence."},
                      {"role": "user", "content": prompt}],
            max_tokens=120, temperature=0)
        txt = r["choices"][0]["message"]["content"].strip()
        if "GIVE_UP" in txt:
            fires["give_up"] += 1
        if "switch" in txt.lower() or "different" in txt.lower() or "instead" in txt.lower():
            fires["switch"] += 1
        out_f.write(json.dumps({"t": i, "mech": "h1" if arm == "on" else "base",
                                "fire": 1 if arm == "on" else 0,
                                "next_action": txt[:200], "level": level, "arm": arm}) + "\n")
    return fires

def emit_check(llm, out_f):
    syn = ("t=41 state=aa11 level=2 score=5 action=CLICK(3,7) next=bb22 progress=no\n"
           "t=42 state=bb22 level=2 score=5 action=CLICK(3,7) next=bb22 progress=no\n"
           "t=43 state=bb22 level=2 score=5 action=CLICK(3,7) next=bb22 progress=no\n"
           "The agent repeats CLICK(3,7) with no progress. Write one playbook rule.\n"
           "Format exactly: RULE: <rule text> | SUPPORT: <game>@<t>=<level>/<score>")
    import re
    res = []
    for temp in (0, 0.7, 0.7):
        r = llm.create_chat_completion(
            messages=[{"role": "system", "content": "You are a game analyst. Output exactly one line."},
                      {"role": "user", "content": syn}],
            max_tokens=200, temperature=temp)
        txt = r["choices"][0]["message"]["content"].strip()
        has_rule = bool(re.search(r"^RULE:", txt, re.M))
        has_ref = bool(re.search(r"\S+@\d+=\d+/\d+", txt))
        res.append({"temp": temp, "text": txt[:300], "hasRule": has_rule, "hasRef": has_ref})
        out_f.write(json.dumps({"t": "emit", "mech": "playbook", "fire": 1 if has_rule else 0,
                                "next_action": txt[:200], "level": 2, "admitted": has_ref}) + "\n")
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--arms", default="off,on")
    ap.add_argument("--turns", type=int, default=100)
    ap.add_argument("--emit-check", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    llm = load_llm(a.model)
    summary = {"model": a.model, "arms": {}}
    with open(a.out, "w") as f:
        for arm in a.arms.split(","):
            summary["arms"][arm] = run_arm(llm, arm.strip(), a.turns, f)
        if a.emit_check:
            summary["emission"] = emit_check(llm, f)
    print(json.dumps(summary, indent=1))

if __name__ == "__main__":
    main()
