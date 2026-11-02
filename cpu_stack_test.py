# cpu_stack_test.py â CPU proxy for the ARC-3 stack (GH Actions + Kaggle CPU).
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


# HYPER-NICHE STACK (additive, 2026-11-02) â timer-bar/macro hash, dispatch, combo, temp-diverse, simulator gate.
import hashlib
def frame_full_hash(grid): return hashlib.md5(bytes(grid)).hexdigest()
def frame_content_hash(grid, rows=62, cols=64):
  return hashlib.md5(bytes(grid[:rows*cols])).hexdigest()
def macro_stat_hash(grid):
  n = len(grid); mean = sum(grid)/n
  var = sum((x-mean)**2 for x in grid)/n; std = var**0.5
  return (round(mean,1), round(std,1), sum(1 for x in grid if x), len(set(grid)))
def hyper_hash_selftest(out_f):
  W=64; base=[(r*W+c)%7 for r in range(64) for c in range(W)]
  fulls=set(); contents=set(); macros=set()
  for t in range(6):
    g=list(base)
    for c in range(0,12+2*t,1): g[63*W+c]=9
    fulls.add(frame_full_hash(g)); contents.add(frame_content_hash(g)); macros.add(macro_stat_hash(g))
  res={"full_changes":len(fulls)>1,"content_stable":len(contents)==1,"macro_stable":len(macros)==1,
       "full_n":len(fulls),"content_n":len(contents),"macro_n":len(macros)}
  out_f.write(__import__("json").dumps({"t":"hyper-hash","mech":"hash","fire":1 if res["content_stable"] else 0,"next_action":str(res),"level":0,"arm":"hyper"})+"\n")
  return res
def dispatch_prompt(avail):
  s=set(avail)
  if 6 in s and any(a in s for a in (1,2,3,4,5)): return "ARC-PUZZLE: grid quadrants, color cycling. "
  if s<={1,2,3,4}: return "MOVEMENT: corridors, object tracking, reach target. "
  if s=={6}: return "CLICK-ONLY: identify interactive targets from static screenshot. "
  return "GENERAL: "
def hyper_dispatch_selftest():
  return {"arc":dispatch_prompt([1,2,3,4,5,6])[:9],"move":dispatch_prompt([1,2,3,4])[:8],"click":dispatch_prompt([6])[:10]}
def temp_diverse_sample(llm, prompt, out_f=None):
  outs=[]
  for temp in (0.0,0.55,1.0):
    try:
      r=llm.create_chat_completion(messages=[{"role":"system","content":"Reply one line: CONTINUE or GIVE_UP, then one sentence."},{"role":"user","content":prompt}],max_tokens=120,temperature=temp)
      outs.append(r["choices"][0]["message"]["content"].strip()[:200])
    except Exception as e: outs.append("ERR:"+str(e)[:60])
  distinct=len(set(outs)); switch=sum(1 for o in outs if "switch" in o.lower() or "different" in o.lower() or "instead" in o.lower())
  if out_f is not None:
    out_f.write(__import__("json").dumps({"t":"tempdiv","mech":"tempdiv","fire":1 if distinct>=2 else 0,"next_action":"distinct %d/3 switch %d"%(distinct,switch),"level":0,"arm":"hyper","outs":outs})+"\n")
  return {"outs":outs,"distinct":distinct,"switch":switch}
HELDOUT=[(s,a,(s*3+a)%17) for s in range(10,15) for a in (1,2)][:10]
def score_heldout(fn):
  good=0
  for s,a,n in HELDOUT:
    try:
      if int(fn(s,a))==n: good+=1
    except Exception: pass
  return good
FENCE="```"
def simulator_gate_test(llm, out_f, tries=2):
  trans=[(s,a,(s*3+a)%17) for s in range(10) for a in (1,2)][:20]
  body="\n".join("(%d,%d)->%d"%(s,a,n) for s,a,n in trans)
  prompt=("Write ONE python function step(state,action) returning next state. Observed transitions:\n"+body+"\nRule is arithmetic. Output exactly one fenced python block with the function, no other text.")
  ok=0; detail=[]
  for i in range(tries):
    try:
      r=llm.create_chat_completion(messages=[{"role":"system","content":"Output exactly one python fence."},{"role":"user","content":prompt}],max_tokens=300,temperature=0.0)
      txt=r["choices"][0]["message"]["content"]
      import re
      m=re.search(FENCE+r"python(.*?)"+FENCE,txt,re.S) or re.search(FENCE+r"(.*?)"+FENCE,txt,re.S)
      code=(m.group(1) if m else txt)
      ns={}
      exec(code,ns)
      fn=ns.get("step") or ns.get("f") or ns.get("next_state")
      good=0
      if callable(fn):
        for s,a,n in trans:
          try:
            if int(fn(s,a))==n: good+=1
          except Exception: pass
        held=score_heldout(fn)
        out_f.write(__import__("json").dumps({"t":"sim-heldout-%d"%i,"mech":"simcontrol","fire":1 if held>=8 else 0,"next_action":"heldout %d/10 (train %d/20)"%(held,good),"level":0,"arm":"hyper"})+"\n")
      detail.append(good); ok=max(ok,good)
      out_f.write(__import__("json").dumps({"t":"sim-%d"%i,"mech":"simulator","fire":1 if good>=16 else 0,"next_action":"repro %d/20"%good,"level":0,"arm":"hyper"})+"\n")
    except Exception as e:
      detail.append("ERR:"+str(e)[:60])
  return {"best":ok,"detail":detail,"pass":ok>=16}

def hier_decompose_probe(llm, out_f, tries=2):
  import re as _re
  prompt = ("Game: 8x8 grid, robot at (1,1), red key at (5,2), locked door at (7,7). Exit beyond door. "
    "Reply with exactly 3 numbered subgoals, each naming a grid entity and one action verb (MOVE/GET/OPEN/GO).")
  verbs = ("move","get","open","go","push","press","collect","unlock","reach","carry")
  ents = ("robot","key","door","exit","grid","(1,1)","(5,2)","(7,7)")
  best = 0; detail = []
  for i in range(tries):
    try:
      r = llm.create_chat_completion(messages=[{"role":"system","content":"Reply with exactly 3 numbered subgoals."},{"role":"user","content":prompt}],max_tokens=200,temperature=0.2)
      txt = r["choices"][0]["message"]["content"]
      lines = [l for l in txt.strip().split("\n") if _re.match(r"\s*\d+[\).\:] ", l)]
      score = 0
      for l in lines[:3]:
        ll = l.lower()
        if any(v in ll for v in verbs): score += 1
        if any(e in ll for e in ents): score += 1
      ok = 1 if (len(lines) >= 3 and score >= 4) else 0
      detail.append((len(lines), score)); best = max(best, ok)
      out_f.write(__import__("json").dumps({"t":"hier-%d"%i,"mech":"hier","fire":ok,"next_action":"lines %d grounded %d/6"%(len(lines),score),"level":0,"arm":"hyper"})+"\n")
    except Exception as e:
      detail.append("ERR:"+str(e)[:60])
  return {"best":best,"detail":detail,"pass":best>=1}

def simulator_gate_test_relaxed(llm, out_f, tries=2):
  import re
  trans=[(s,a,(s*3+a)%17) for s in range(10) for a in (1,2)][:20]
  body="\n".join("(%d,%d)->%d"%(s,a,n) for s,a,n in trans)
  prompt=("Write ONE python function step(state,action) returning next state. Observed transitions:\n"+body+"\nRule is arithmetic. Output exactly one fenced python block with the function, no other text.")
  def extract_candidates(txt):
    cands=[]
    m=re.search(FENCE+r"python(.*?)"+FENCE,txt,re.S|re.I)
    if m: cands.append(m.group(1))
    m2=re.search(FENCE+r"(.*?)"+FENCE,txt,re.S)
    if m2: cands.append(m2.group(1))
    m3=re.search(r"(def\s+step\s*\(.*?\)\s*:[\s\S]*?)(?:\n\S|\Z)",txt)
    if m3: cands.append(m3.group(1))
    lines=[l for l in txt.split("\n") if re.match(r"\s*(def |import |from |return |for |if |while |[a-zA-Z_][a-zA-Z0-9_]*\s*=)",l)]
    if lines: cands.append("\n".join(lines))
    cands.append(txt)
    return cands
  ok=0; detail=[]; besthits=[]; bestcode=""
  for i in range(tries):
    try:
      r=llm.create_chat_completion(messages=[{"role":"system","content":"Output exactly one python fence."},{"role":"user","content":prompt}],max_tokens=300,temperature=0.0)
      txt=r["choices"][0]["message"]["content"]
      best=0
      for code in extract_candidates(txt):
        ns={}
        try:
          exec(code,ns)
        except Exception:
          continue
        fn=ns.get("step") or ns.get("f") or ns.get("next_state") or ns.get("predict") or ns.get("transition")
        if not callable(fn):
          for v in ns.values():
            if callable(v):
              try:
                int(v(0,1)); fn=v; break
              except Exception:
                pass
        if callable(fn):
          good=0; hitpairs=[]
          for s,a,n in trans:
            try:
              if int(fn(s,a))==n: good+=1; hitpairs.append([s,a])
            except Exception:
              pass
          held=score_heldout(fn)
          try:
            _hh=[]
            for _s,_a,_n in HELDOUT:
              try:
                if int(fn(_s,_a))==_n: _hh.append([_s,_a])
              except Exception: pass
          except Exception: _hh=[]
          out_f.write(__import__("json").dumps({"t":"sim-relaxed-heldout-%d"%i,"mech":"simcontrol","fire":1 if held>=8 else 0,"next_action":"heldout %d/10 (train %d/20)"%(held,good),"level":0,"arm":"hyper","hits":hitpairs,"heldhits":_hh})+"\n")
          if good>best: besthits=hitpairs; bestcode=code[:500]
          best=max(best,good)
      detail.append(best); ok=max(ok,best)
      out_f.write(__import__("json").dumps({"t":"sim-relaxed-%d"%i,"mech":"simulator","fire":1 if best>=16 else 0,"next_action":"repro %d/20"%best,"level":0,"arm":"hyper","hits":besthits,"code":bestcode})+"\n")
    except Exception as e:
      detail.append("ERR:"+str(e)[:60])
  return {"best":ok,"detail":detail,"pass":ok>=16}

# HARNESS-SIDE prose parser (entry 802: model emits prose, harness extracts structure).
# parse_procedure_prose(txt) -> steps=[(verb, entity)...] in mention order, position, next.
def parse_procedure_prose(txt):
  import re as _re
  ll = txt.lower()
  steps = [(m.group(1), m.group(2)) for m in
    _re.finditer(r"\b(move|get|open|unlock|go|exit|push|collect|carry|use|take|grab)\b[^.\n]{0,40}?\b(robot|key|door|exit)\b", ll)]
  ded = []
  for s in steps:
    if not ded or s != ded[-1]: ded.append(s)
  pos = None
  m2 = _re.search(r"(current|now|at|step)\D{0,10}([1-9])", ll)
  if m2: pos = int(m2.group(2))
  return {"steps": ded, "n": len(ded), "pos": pos, "next": ded[-1] if ded else (None, None)}

# GOAL-AS-PROCEDURE probe (entry 797 structural gap, Quome diagnosis).
# Part A: emit an ordered procedure + current step + next action from a mid-run state.
# Part B: A/B stall vignette, base vs goal-ledger arm; fire = procedure-consistent next verb.
def goal_ledger_probe(llm, out_f, tries=2):
  import re as _re
  state = ("8x8 grid. Ordered plan: 1 MOVE robot to key, 2 GET red key, 3 MOVE to door, "
    "4 OPEN locked door, 5 GO exit. Progress: robot HAS key, robot at (6,6), door at (7,7) still locked. "
    "List the ordered steps (1..N), then state CURRENT step number and the NEXT action.")
  verbs = ("open", "unlock", "go", "exit", "move", "use")
  ents = ("door", "key", "exit", "robot")
  best = 0; detail = []
  # entry 803: base vs harness-injected progress state (acting-class test)
  state_arms = (("base", state),
    ("injected", state + " HARNESS RECORD (authoritative, overrides memory): key OBTAINED at t=12, steps 1-3 COMPLETE. "
      "You are at step 4 of 5. Do NOT repeat completed steps. State CURRENT step and NEXT action."))
  for i in range(tries):
    try:
      for sarm, sprompt in state_arms:
        r = llm.create_chat_completion(
          messages=[{"role": "system", "content": "Reply with numbered steps, then CURRENT step and NEXT action."},
                    {"role": "user", "content": sprompt}],
          max_tokens=250, temperature=0.2)
        txt = r["choices"][0]["message"]["content"]
        lines = [l for l in txt.strip().split("\n") if _re.match(r"\s*\d+[\).\:] ", l)]
        ll = txt.lower()
        has_steps = len(lines) >= 3
        has_pos = bool(_re.search(r"(current|step)\s*(is|:)?\s*[34]", ll))
        has_next = any(v in ll for v in verbs) and any(e in ll for e in ents)
        ok = 1 if (has_steps and has_pos and has_next) else 0
        best = max(best, ok)
        detail.append((len(lines), has_pos, has_next))
        # harness-side parse (entry 802): same prose, harness extracts structure
        pp = parse_procedure_prose(txt)
        pok = 1 if (pp["n"] >= 2 and pp["next"][1] in ("door", "exit", "key")) else 0
        # entry 803: step-4 consistency = parsed NEXT is open-door/go-exit (not restart at key)
        step4 = 1 if (pp["next"] in (("open", "door"), ("unlock", "door"), ("go", "exit"), ("exit", "exit"), ("go", "door"), ("move", "door"))) else 0
        out_f.write(__import__("json").dumps({"t": "goal-emit-%d" % i, "mech": "goal", "fire": ok,
          "next_action": "steps %d pos %d next %d" % (len(lines), has_pos, has_next),
          "level": 0, "arm": "goal"}) + "\n")
        out_f.write(__import__("json").dumps({"t": "goal-parse-%d-%s" % (i, sarm), "mech": "goalparse", "fire": pok,
          "next_action": "parsed %d steps next %s/%s step4 %d raw %s" % (pp["n"], pp["next"][0], pp["next"][1], step4, txt[:300]),
          "level": 0, "arm": "goal"}) + "\n")
      # Part B: stall A/B
      stall = ("You used 180 actions on level 7 (human par 40), no score increase in 30 actions. "
        "Reply one line: CONTINUE or GIVE_UP, then one sentence.")
      for arm, tail in (("base", ""), ("ledger", " Goal ledger: GOAL exit via door; DONE got key, at door; NEXT OPEN door then GO exit. State NEXT now.")):
        r2 = llm.create_chat_completion(
          messages=[{"role": "system", "content": "Reply one line: CONTINUE or GIVE_UP, then one sentence."},
                    {"role": "user", "content": stall + tail}],
          max_tokens=120, temperature=0)
        t2 = r2["choices"][0]["message"]["content"].strip()
        l2 = t2.lower()
        proc = 1 if (any(v in l2 for v in ("open", "unlock", "door")) or ("go" in l2 and "exit" in l2)) else 0
        out_f.write(__import__("json").dumps({"t": "goal-ab-%d-%s" % (i, arm), "mech": "goal",
          "fire": proc, "next_action": t2[:200], "level": 7, "arm": arm}) + "\n")
    except Exception as e:
      detail.append("ERR:" + str(e)[:60])
  return {"best": best, "detail": detail, "pass": best >= 1}

# STRUCTURED-LOG synthesis probe (paper-mine transfer area): same arithmetic
# transitions as the sim gate, but the prompt forces ENTITIES/RULE/EDGE lines
# before the fenced step(). Verdict = format-follow + held-out delta vs relaxed.
def sim_structured_test(llm, out_f, tries=2):
  import re
  trans = [(s, a, (s * 3 + a) % 17) for s in range(10) for a in (1, 2)][:20]
  body = "\n".join("(%d,%d)->%d" % (s, a, n) for s, a, n in trans)
  prompt = ("Observed transitions:\n" + body + "\nRule is arithmetic.\n"
    "First write exactly 3 lines starting ENTITIES: / RULE: / EDGE: (your hypothesis), "
    "then ONE fenced python block with function step(state,action) returning next state, no other text.")
  ok = 0; detail = []
  for i in range(tries):
    try:
      r = llm.create_chat_completion(
        messages=[{"role": "system", "content": "Write 3 hypothesis lines, then exactly one python fence."},
                  {"role": "user", "content": prompt}],
        max_tokens=400, temperature=0.0)
      txt = r["choices"][0]["message"]["content"]
      fmt = sum(1 for k in ("ENTITIES:", "RULE:", "EDGE:") if k in txt)
      m = re.search(FENCE + r"python(.*?)" + FENCE, txt, re.S | re.I) or re.search(FENCE + r"(.*?)" + FENCE, txt, re.S)
      best = 0; held = 0
      if m:
        ns = {}
        try:
          exec(m.group(1), ns)
        except Exception:
          pass
        fn = ns.get("step") or ns.get("f") or ns.get("next_state") or ns.get("predict") or ns.get("transition")
        if callable(fn):
          for s, a, n in trans:
            try:
              if int(fn(s, a)) == n: best += 1
            except Exception:
              pass
          held = score_heldout(fn)
      detail.append((fmt, best, held)); ok = max(ok, held)
      out_f.write(__import__("json").dumps({"t": "sim-struct-%d" % i, "mech": "simstruct",
        "fire": 1 if held >= 8 else 0,
        "next_action": "fmt %d/3 train %d/20 heldout %d/10" % (fmt, best, held),
        "level": 0, "arm": "hyper"}) + "\n")
    except Exception as e:
      detail.append("ERR:" + str(e)[:60])
  return {"best": ok, "detail": detail, "pass": ok >= 8}

def sg_intent_probe(llm, out_f, tries=2):
  # SG-FEED probe (entry 815, minimal-set pre-flight): does 3B emit intent-marked
  # prose our pp parser captures? Part B/C are model-free logic (must pass or driver bug:
  # do NOT dispatch on failure). Part A is the model read (fed>=1 = machinery has input).
  import re as _re2
  _V = ("move","get","open","unlock","go","exit","push","collect","carry","use","take","grab","click","press","solve","clear","reach","find","map")
  _E = ("robot","key","door","exit","button","box","target","switch","lever","gate","tile","room","level","path")
  _I = ("need to","needs to","next","then","should","plan to","going to","try to","must","will")
  def _subs(text):
    out = []
    try:
      for _ln in str(text or "").splitlines():
        _s = _ln.strip()
        if len(_s) < 8 or len(_s) > 220: continue
        if _s.upper().startswith("SG:"):
          _t = _s[3:].strip()
          if len(_t) > 4 and _t not in out: out.append(_t[:160])
          continue
        _l = _s.lower()
        if any(_k in _l for _k in _I):
          _v = next((_v for _v in _V if _v in _l), "")
          _e = next((_e for _e in _E if _e in _l), "")
          if _v and _e and _s not in out: out.append(_s[:160])
        if len(out) >= 4: break
    except Exception: pass
    return out
  # Part B: fixed feed cases (expect 3 feed / 3 ignore)
  _cases = [("I need to get the key next", True), ("plan to move robot to door", True),
    ("then go to exit", True), ("CLICK(3,7)", False), ("the sky is blue today", False), ("ok", False)]
  _bok = sum(1 for _t, _w in _cases if ((_subs(_t) and True) or False) == _w)
  out_f.write(__import__("json").dumps({"t": "sg-feed-unit", "mech": "proseparse", "fire": 1 if _bok == 6 else 0,
    "next_action": "feed-logic %d/6" % _bok, "level": 0, "arm": "unit"}) + "\n")
  # Part C: synthetic refusal (passed subgoal "get key", cur idx 1)
  _sgs = [{"text": "get the key", "stalls": 0, "budget": 0.0}, {"text": "open the door", "stalls": 0, "budget": 0.0}]
  def _ref(prop):
    _p = str(prop or "").lower()
    _t0 = (_sgs[0].get("text", "") or "").lower()
    if not _t0: return 0
    import re as _rx
    _stop = ("with","from","that","this","then","into","have","has","are","was","were","been","the")
    _syn = {"move": ("move","go"), "get": ("get","take","grab","carry","collect"), "open": ("open","unlock")}
    _ws = [w for w in _rx.findall(r"[a-z]+", _t0) if w not in _stop]
    for _w in _ws:
      _alts = _syn.get(_w, (_w,))
      if any(_a in _p for _a in _alts): return 1
    return 0
  _rok = 1 if (_ref("GET key at (5,2)") == 1 and _ref("OPEN door") == 0) else 0
  out_f.write(__import__("json").dumps({"t": "sg-refuse-unit", "mech": "proseparse", "fire": _rok,
    "next_action": "refuse-logic %d/2" % (_rok * 2), "level": 0, "arm": "unit"}) + "\n")
  # Part A: model emission read (2 tries, stuck vignette -> plan prose -> pp parse)
  _fed = 0; _det = []
  for _i in range(tries):
    try:
      _r = llm.create_chat_completion(
        messages=[{"role": "system", "content": "Describe your plan in 2-3 short sentences."},
                  {"role": "user", "content": "8x8 grid, robot at (1,1), key at (5,2), locked door at (7,7), exit beyond. You are stuck after 40 actions with no progress. Say what you need to do next, naming the robot, key, door or exit."}],
        max_tokens=200, temperature=0.2)
      _txt = _r["choices"][0]["message"]["content"]
      _f = _subs(_txt)
      _fed = max(_fed, len(_f))
      _det.append(len(_f))
      out_f.write(__import__("json").dumps({"t": "sg-emit-%d" % _i, "mech": "proseparse", "fire": 1 if _f else 0,
        "next_action": "fed %d raw %s" % (len(_f), _txt[:200]), "level": 0, "arm": "sg"}) + "\n")
    except Exception as _e:
      _det.append("ERR:" + str(_e)[:60])
  return {"feed_logic": _bok, "refuse_logic": _rok, "fed_best": _fed, "detail": _det,
          "pass": _bok == 6 and _rok == 1, "model_has_input": _fed >= 1}

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
        try:
            summary["hyper_hash"] = hyper_hash_selftest(f)
            summary["hyper_dispatch"] = hyper_dispatch_selftest()
            try:
                summary["temp_diverse"] = temp_diverse_sample(llm, "You used 180 actions on level 7 (human par 40), no score increase in 30 actions. Reply one line: CONTINUE or GIVE_UP, then one sentence.", f)
            except Exception as e:
                summary["temp_diverse_err"] = str(e)[:120]
        except Exception as e:
            summary["hyper_hash_err"] = str(e)[:120]
        try:
            summary["simulator"] = simulator_gate_test(llm, f, tries=2)
        except Exception as e:
            summary["simulator_err"] = str(e)[:120]
        try:
            summary["simulator_relaxed"] = simulator_gate_test_relaxed(llm, f, tries=2)
        except Exception as e:
            summary["simulator_relaxed_err"] = str(e)[:120]
        try:
            summary["hier"] = hier_decompose_probe(llm, f, tries=2)
        except Exception as e:
            summary["hier_err"] = str(e)[:120]
        try:
            summary["goal_ledger"] = goal_ledger_probe(llm, f, tries=2)
        except Exception as e:
            summary["goal_ledger_err"] = str(e)[:120]
        try:
            summary["sim_structured"] = sim_structured_test(llm, f, tries=2)
        except Exception as e:
            summary["sim_structured_err"] = str(e)[:120]
        try:
            summary["sg_intent"] = sg_intent_probe(llm, f, tries=2)
        except Exception as e:
            summary["sg_intent_err"] = str(e)[:120]
    print(json.dumps(summary, indent=1))

if __name__ == "__main__":
    main()
