#!/usr/bin/env python3
"""
Local dev server for the Light Fitting Schedule.

WHY THIS EXISTS
On the Plexus server the AI call is handled by llm-extract.php, which needs
PHP and a Synergy login session. Neither exists on your laptop, so opening
lfs.html off the disk gives you the rules-only tool and no way to tell.

This serves the folder over http://localhost and answers the one request
llm-extract.php would answer, using the SAME prompt file. Python only - no
PHP install, no pip install.

    set ANTHROPIC_API_KEY=sk-ant-...      (Windows cmd)
    $env:ANTHROPIC_API_KEY="sk-ant-..."   (PowerShell)
    python dev-server.py

...or put it in a file called .plexus-anthropic-key in your home folder
(C:\\Users\\plexu\\). Deliberately OUTSIDE this git repo, so there is no way
to commit it to GitHub by accident.

Then open http://localhost:8000/lfs.html and drop a datasheet in.
Every scan prints what was asked, what came back and what it cost.
"""

import base64, json, os, re, sys, urllib.request, urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE      = Path(__file__).resolve().parent
PROMPT_F  = HERE / "extract-prompt.md"
KEY_HOME  = Path.home() / ".plexus-anthropic-key"   # outside the repo - preferred
KEY_LOCAL = HERE / ".anthropic-key"                 # inside the repo - last resort
WS_HOME   = Path.home() / ".plexus-anthropic-workspace"


def _read_text_file(f):
    """Returns (text, note). Tolerates the encodings Windows produces: the `>`
    operator and Out-File default to UTF-16 on Windows PowerShell, Notepad adds
    a UTF-8 BOM. Both look right in an editor and are wrong on the wire."""
    raw = f.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace"), "the file is UTF-16 (PowerShell's default)"
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig", "replace"), "the file starts with a UTF-8 byte-order mark"
    return raw.decode("utf-8", "replace"), ""


def workspace_id():
    """Identity-linked keys must name the workspace the request acts in.
    Ordinary keys do not, and the header is simply omitted for them."""
    w = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if w:
        return w, "ANTHROPIC_WORKSPACE_ID"
    try:
        if WS_HOME.exists():
            w = _read_text_file(WS_HOME)[0].strip().strip("\ufeff").strip()
            if w:
                return w, str(WS_HOME)
    except OSError:
        pass
    return "", ""
MODEL     = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
PORT      = int(os.environ.get("PORT", "8000"))
TEXT_LIMIT = 24000

# the columns the tool is allowed to ask about - same list as the PHP
ALLOWED = {"description", "finish", "dimensions", "ip", "source", "cri",
           "sdcm", "lifetime", "mounting", "driver", "model",
           # not columns: these two compose the MANUFACTURER / MODEL cell
           "manufacturer", "code"}

UNKNOWNS = {"", "unknown", "n/a", "na", "none", "null", "-", "--",
            "not stated", "not specified"}


def key_is_sane(k):
    """Cheap shape test, used to decide which source to trust - not to validate
    the key. Catches the doubled prefix, quotes and truncation."""
    k = (k or "").strip().strip("\ufeff")
    return (k.startswith("sk-ant-") and not k[7:].startswith("sk-")
            and 95 <= len(k) <= 120 and not any(c in k for c in " \r\n\t\"'"))


def api_key():
    """Env var first, then a key file in your home folder, then one beside this
    script. The home folder is preferred because this directory is a git repo
    pointed at GitHub - a key committed there is a key you have to revoke.

    EXCEPTION: a malformed env var never beats a well-formed file. A stale
    ANTHROPIC_API_KEY set at Windows User scope comes back in every new shell
    and silently shadows a key file that works - which cost an afternoon once,
    so the good key now wins regardless of where it lives."""
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if k and not key_is_sane(k):
        for f in (KEY_HOME, KEY_LOCAL):
            try:
                if f.exists() and key_is_sane(_read_text_file(f)[0]):
                    return (_read_text_file(f)[0].strip().strip("\ufeff").strip(),
                            str(f), f is KEY_LOCAL,
                            "ignored a malformed ANTHROPIC_API_KEY (%s) in favour of "
                            "this file - clear the variable permanently with: "
                            '[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY",'
                            '$null,"User")' % (k[:11] + "..."))
            except OSError:
                pass
    if k:
        return k, "ANTHROPIC_API_KEY", False, ""
    for f, risky in ((KEY_HOME, False), (KEY_LOCAL, True)):
        try:
            if not f.exists():
                continue
        except OSError:
            continue
        text, note = _read_text_file(f)
        k = text.strip().strip("\ufeff").strip()
        if k:
            return k, str(f), risky, note
    return "", "", False, ""


def load_prompt():
    """Same file the PHP reads, so the two cannot drift apart."""
    lines = PROMPT_F.read_text(encoding="utf-8").splitlines()
    # discard the comment header: everything before the first marker LINE.
    # Searching for the marker text instead would match a mention of it in
    # the comments, which is exactly the bug this replaced.
    while lines and not lines[0].startswith("==="):
        lines.pop(0)
    body = "\n".join(lines).split("===SYSTEM===", 1)[1]
    system, user = body.split("===USER===", 1)
    return system.strip(), user.strip()


ATTACHED = ("The datasheet is attached to this message as a PDF. Read it as a "
            "page: use the table columns, the panel each value sits in, and the "
            "dimension drawings. Do not rely on reading order alone.")


def call_claude(fields, text, pdf_b64=None):
    key = api_key()[0]
    if not key:
        return 501, {"error": "No API key configured"}

    system, user_tpl = load_prompt()
    wanted = "".join('  "%s": %s\n' % (k, v) for k, v in fields.items())

    if pdf_b64:
        # Send the PDF itself. Flattening a datasheet to text destroys the
        # thing that tells a human which number belongs to which label, and
        # leaves every decoy behind: "Luminous Length 628mm" reads exactly like
        # "Dimensions 650mm" once the panels are gone, and a dimension drawn on
        # a diagram does not survive at all. The document block goes first,
        # which is what Anthropic recommends for extraction accuracy.
        user = user_tpl.replace("{{FIELDS}}", wanted).replace("{{TEXT}}", ATTACHED)
        content = [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": user},
        ]
    else:
        user = user_tpl.replace("{{FIELDS}}", wanted).replace("{{TEXT}}", text[:TEXT_LIMIT])
        content = user

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 1024,
        "temperature": 0,
        "system": system,
        "messages": [
            {"role": "user", "content": content},
            # prefill the opening brace so the reply cannot be wrapped in prose
            {"role": "assistant", "content": "{"},
        ],
    }).encode("utf-8")

    headers = {"content-type": "application/json",
               "x-api-key": key,
               "anthropic-version": "2023-06-01"}
    ws = workspace_id()[0]
    if ws:
        headers["anthropic-workspace-id"] = ws
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        # Anthropic echoes the workspace the request ran in on the response
        # itself, error responses included. That is the only way to learn the
        # Default Workspace's id - the console does not list it.
        hint = ""
        try:
            hint = e.headers.get("anthropic-workspace-id") or ""
        except Exception:
            pass
        print("   !! API %s: %s" % (e.code, detail))
        return 502, {"error": "Upstream failed", "status": e.code,
                     "detail": detail, "workspace_hint": hint}
    except Exception as e:
        print("   !! %s" % e)
        return 502, {"error": "Upstream failed", "detail": str(e)}

    content = "{" + (out.get("content", [{}])[0].get("text", ""))
    try:
        vals = json.loads(content)
    except Exception:
        start, end = content.find("{"), content.rfind("}")
        try:
            vals = json.loads(content[start:end + 1])
        except Exception:
            print("   !! unparseable reply: %r" % content[:200])
            return 502, {"error": "Could not read the model response"}

    clean, declined, sources = {}, [], {}
    for k in fields:
        raw = vals.get(k)
        # New shape: {"n": <count>, "v": <value>, "src": <quote>}. The count is
        # enforced HERE rather than trusted: a field the sheet gives two values
        # for is blanked no matter how confidently v was filled in. Asking the
        # model to remember a rule failed; asking it to show its working and
        # letting code apply the rule does not.
        if isinstance(raw, dict):
            try:
                n = int(raw.get("n"))
            except (TypeError, ValueError):
                n = -1
            v = raw.get("v") if isinstance(raw.get("v"), str) else ""
            src = str(raw.get("src") or "")[:160]
            if n != 1 or not v.strip() or v.strip().lower() in UNKNOWNS:
                declined.append("%s(n=%s)" % (k, n if n >= 0 else "?"))
                continue
            # The quote can convict the value. If the only evidence offered is
            # an availability line, this is an option the product can have, not
            # what it is - the "Dali Available: Yes" case. Cheap and precise:
            # a legitimate source quote does not need these words.
            if re.search(r"\b(available|optional|on request|can be supplied|upon request)\b",
                         src, re.I):
                declined.append("%s(quoted an availability line)" % k)
                continue
            clean[k] = v.strip()[:120]
            if src:
                sources[k] = src
            continue
        # Old shape: a bare string. Still accepted so an older prompt works.
        if not isinstance(raw, str) or raw.strip().lower() in UNKNOWNS:
            declined.append(k)
            continue
        clean[k] = raw.strip()[:120]

    u = out.get("usage", {})
    cost = (u.get("input_tokens", 0) / 1e6 * 1.00) + (u.get("output_tokens", 0) / 1e6 * 5.00)
    print("   input  %s" % ("PDF pages (the model sees the layout)" if pdf_b64
                                        else "flattened text (no PDF sent)"))
    print("   model  %s" % MODEL)
    print("   tokens in=%s out=%s   ~US$%.4f this scan"
          % (u.get("input_tokens", 0), u.get("output_tokens", 0), cost))
    print("   filled   %s" % (", ".join(sorted(clean)) or "(nothing)"))
    print("   declined %s" % (", ".join(sorted(declined)) or "(nothing)"))
    for k in sorted(clean):
        print("       %-11s %-34s %s"
              % (k, clean[k].replace("\n", " / ")[:34],
                 ("<- " + sources[k][:44]) if k in sources else ""))
    out = dict(clean)
    if sources:
        out["_src"] = sources
    return 200, out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def end_headers(self):
        # A dev server must never be cached. A stale lfs.html keeps asking for
        # a stale lfs.css, which looks exactly like a change that did not work
        # - and costs an afternoon of arguing with the wrong file.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # the interesting logging is done by hand below

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.split("?")[0].endswith("llm-extract.php"):
            self._send(404, {"error": "Not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            self._send(400, {"error": "Bad request: %s" % e})
            return

        fields = {k: v for k, v in (req.get("fields") or {}).items() if k in ALLOWED}
        text = req.get("text") or ""
        pdf = req.get("pdf") or ""
        if not fields or not (text.strip() or pdf):
            self._send(400, {"error": "Nothing to extract"})
            return

        print("\n>> scan: asked for %d fields, %s"
              % (len(fields), ("%.1f MB PDF" % (len(pdf) * 0.75 / 1e6)) if pdf
                 else "%d chars of text" % len(text)))
        code, obj = call_claude(fields, text, pdf)
        self._send(code, obj)


def check_key():
    """python dev-server.py --check-key

    'API key is invalid' means the string we sent is not a key Anthropic
    recognises. On Windows that is usually the FILE, not the key: PowerShell's
    default redirection writes UTF-16 with a byte-order mark, and `set X="sk-.."`
    in cmd keeps the quote characters. Both produce a key that looks perfect in
    a text editor and is wrong on the wire. This reports the shape of what we
    are actually sending, never the key itself, then tries one real call."""
    key, src, _, note = api_key()
    print("\n  Key check")
    print("  " + "-" * 44)
    if not key:
        print("  No key found at all.")
        print("    env ANTHROPIC_API_KEY : not set")
        print("    %s : %s" % (KEY_HOME, "exists" if KEY_HOME.exists() else "not there"))
        print("    %s : %s" % (KEY_LOCAL, "exists" if KEY_LOCAL.exists() else "not there"))
        return
    print("  source   %s" % src)
    problems = []

    # Show the workspace id too. Leaving it invisible cost a round trip: a
    # placeholder pasted verbatim from an instruction looks identical to no
    # workspace at all from the outside, but produces a different API error.
    wsid, wssrc = workspace_id()
    if wsid:
        print("  workspace %s (from %s)" % (wsid, wssrc))
        if "..." in wsid or not wsid.startswith("wrkspc_"):
            clear = ('Remove-Item Env:\\%s' % wssrc) if not wssrc.startswith(("/", "C:", "\\")) \
                    else ('Remove-Item "%s"' % wssrc)
            problems.append("the workspace id is %r, which is the literal placeholder "
                            "from the instructions rather than a real id. Clear it:\n"
                            "        %s\n"
                            "      then either put your real wrkspc_... id there, or "
                            "use a workspace-scoped API key and skip it entirely"
                            % (wsid, clear))
    else:
        print("  workspace not set (fine for a workspace-scoped key)")
    if note:
        # the encoding notes get a tail; the "ignored a bad env var" note is
        # already a complete sentence and must not have one bolted on
        if "UTF" in note or "byte-order" in note:
            note += (" - harmless here because this script now decodes it, but "
                     "rewrite it as plain ASCII so nothing else trips")
        problems.append(note)
    if key != key.strip():
        problems.append("the key has leading or trailing whitespace")
    k = key.strip()
    if k.startswith("\ufeff"):
        problems.append("the key starts with a byte-order mark - the file was "
                        "written by PowerShell redirection (> or Out-File without "
                        "-Encoding ascii)")
        k = k.lstrip("\ufeff")
    if k[:1] in "\"'" or k[-1:] in "\"'":
        problems.append("the key is wrapped in quote characters - `set KEY=\"sk-...\"` in cmd "
                        "keeps the quotes; drop them")
    if "\x00" in k:
        problems.append("the key contains null bytes - rewrite the file as ASCII")
    if any(c in k for c in " \r\n\t"):
        problems.append("the key contains a space or line break in the middle")
    if not k.startswith("sk-ant-"):
        problems.append("the key does not start with 'sk-ant-' (got %r)" % k[:8])
    elif k[7:].startswith("sk-"):
        # 'sk-ant-sk-ant-api03-...' - a paste landed on top of a prefix that was
        # already there. Passes a naive startswith() check, which is why it is
        # worth testing for explicitly.
        problems.append("the key has 'sk-ant-' on the front TWICE - a paste landed "
                        "on top of an existing prefix. Drop the leading 'sk-ant-' "
                        "and use the key exactly as the console gave it to you")
    elif not (95 <= len(k) <= 120):
        problems.append("the key is %d characters; Anthropic keys are around 108. "
                        "Check nothing was truncated or duplicated in the paste" % len(k))

    print("  length   %d characters" % len(key))
    print("  looks    %s...%s" % (k[:11], k[-4:]))
    if problems:
        print("\n  PROBLEMS FOUND:")
        for p in problems:
            print("    - %s" % p)
        print("\n  Fix, in PowerShell:")
        print('    "sk-ant-..." | Out-File -NoNewline -Encoding ascii "$HOME\\.plexus-anthropic-key"')
    else:
        print("  shape    looks fine - nothing malformed about the string")

    print("\n  Trying one real call...")
    code, obj = call_claude({"ip": "Ingress protection rating, e.g. IP20."},
                            "Kup Recessed 72 1x IP55 LED DE\nIP Rating 55")
    if code == 200:
        print("\n  WORKING. The key is good and the model answered: %s" % obj)
    elif obj.get("status") == 401:
        print("\n  Still rejected. The string is being sent correctly, so the key")
        print("  itself is wrong - revoked, from a different org, or a typo.")
        print("  Make a fresh one at console.anthropic.com > API keys and retry.")
    elif obj.get("status") == 404:
        print("\n  Key is FINE - the model id was rejected instead. Set another:")
        print("     $env:ANTHROPIC_MODEL=\"claude-haiku-4-5\"")
    elif obj.get("status") in (400, 402, 403):
        detail = obj.get("detail", "")
        print("\n  The KEY IS GOOD - it authenticated. The request was refused (%s)."
              % obj.get("status"))
        if "workspace" in detail.lower():
            hint = obj.get("workspace_hint") or ""
            print("  The key is not scoped to a workspace, so every request has to")
            print("  name the one it acts in.")
            if hint:
                print()
                print("  The API told us which workspace this key belongs to:")
                print("      %s" % hint)
                print("  Save it and you are done - in PowerShell:")
                print('      "%s" | Out-File -NoNewline -Encoding ascii "$HOME\\.plexus-anthropic-workspace"' % hint)
            else:
                print()
                print("  Two ways out, easiest first:")
                print("   1. In the console, create an API key scoped TO a workspace.")
                print("      Those need no header at all and this script will just work.")
                print("   2. Find the id: Settings > Workspaces, the ID column.")
                print("      The DEFAULT workspace is deliberately not listed there -")
                print("      if that is where your key lives, use option 1.")
                print('      Then: "wrkspc_..." | Out-File -NoNewline -Encoding ascii "$HOME\\.plexus-anthropic-workspace"')
        else:
            print("  Often no credit on the account: console.anthropic.com > Billing.")
            print("  The API said: %s" % detail[:300])
    print()


# ---------------------------------------------------------------- test mode

def fields_from_lfs():
    """The field descriptions live in lfs.js (LLM.FIELDS) because the browser
    decides which ones to ask about. Parsed out rather than duplicated here, so
    editing them in one place changes what this harness tests."""
    src = (HERE / "lfs.js").read_text(encoding="utf-8", errors="replace")
    i = src.index("FIELDS: {")
    block = src[i + len("FIELDS: {"): src.index("\n    },", i)]
    out = {}
    for m in re.finditer(r"^\s*(\w+):\s*'((?:[^'\\]|\\.)*)'", block, re.M):
        out[m.group(1)] = m.group(2).replace("\\'", "'").replace("\\\\", "\\")
    if not out:
        raise RuntimeError("could not read LLM.FIELDS out of lfs.js")
    return out


def norm(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def match_expected(expected, filename):
    """Match on a distinctive fragment of the name rather than the whole thing.
    Supplier filenames are long, punctuated and get renamed; keying an
    expected.json to them exactly means it silently scores nothing, which looks
    identical to a perfect run of zero checks."""
    fn = norm(filename)
    best = {}
    for key, want in expected.items():
        if key.startswith("_"):
            continue
        k = norm(key)
        if k and (k in fn or fn in k) and len(k) > len(norm(best.get("_key", ""))):
            best = dict(want)
            best["_key"] = key
    best.pop("_key", None)
    return best


def run_tests(folder):
    """python dev-server.py --test [folder]

    Runs the real extraction over every PDF in a folder and prints what came
    back. Put an expected.json beside them - {"file.pdf": {"ip": "IP55", ...}}
    with "UNKNOWN" for fields that SHOULD come back blank - and it scores
    itself, so you can tell whether a prompt change actually helped instead of
    eyeballing one sheet and hoping."""
    folder = Path(folder)
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print("No PDFs in %s" % folder)
        return
    fields = fields_from_lfs()
    exp_f = folder / "expected.json"
    expected = json.loads(exp_f.read_text(encoding="utf-8")) if exp_f.exists() else {}
    print("\n  %d datasheets, %d fields each%s\n"
          % (len(pdfs), len(fields), ", scoring against expected.json" if expected else ""))

    right = wrong = blank_ok = blank_bad = 0
    for f in pdfs:
        b64 = base64.b64encode(f.read_bytes()).decode()
        code, got = call_claude(fields, "", b64)
        print("=" * 72)
        print(f.name[:70])
        if code != 200:
            print("   ERROR %s %s" % (code, got))
            continue
        got.pop("_src", None)
        want = match_expected(expected, f.name)
        if expected and not want:
            print("   (no entry in expected.json - not scored)")
        for k in fields:
            v = got.get(k, "")
            line = "   %-11s %s" % (k, (v or "-").replace("\n", " / ")[:52])
            if k in want:
                w = want[k]
                if norm(w) in ("unknown", ""):
                    ok = not v
                    blank_ok += ok; blank_bad += (not ok)
                    line += "" if ok else "   <- should be BLANK"
                elif not v:
                    blank_bad += 1
                    line += "   <- MISSED, expected %r" % w
                else:
                    ok = norm(w) in norm(v) or norm(v) in norm(w)
                    right += ok; wrong += (not ok)
                    line += "" if ok else "   <- WRONG, expected %r" % w
            print(line)

    if expected:
        tot = right + wrong + blank_ok + blank_bad
        print("\n" + "=" * 72)
        print("  correct value        %d" % right)
        print("  wrong value          %d   <- the ones that reach a drawing" % wrong)
        print("  correctly blank      %d" % blank_ok)
        print("  wrongly blank/filled %d" % blank_bad)
        if tot:
            print("  SCORE                %d%%" % round(100 * (right + blank_ok) / tot))
    print()


def main():
    if "--test" in sys.argv:
        i = sys.argv.index("--test")
        run_tests(sys.argv[i + 1] if len(sys.argv) > i + 1 else ".")
        return
    if "--check-key" in sys.argv:
        check_key()
        return
    if not PROMPT_F.exists():
        sys.exit("Missing %s - it must sit next to this script." % PROMPT_F.name)
    key, src, risky, note = api_key()
    print("\n  Light Fitting Schedule - local dev server")
    print("  " + "-" * 44)
    print("  folder   %s" % HERE)
    print("  model    %s" % MODEL)
    if key:
        print("  api key  found in %s (...%s)" % (src, key[-4:]))
        if note:
            print("           note: %s" % note)
        wsid, wssrc = workspace_id()
        if wsid:
            print("  workspace %s (from %s)" % (wsid, wssrc))
        if risky:
            print("           WARNING: that file is inside a git repo pointed at")
            print("           GitHub. Add '.anthropic-key' to .gitignore, or move")
            print("           the key to %s" % KEY_HOME)
    else:
        print("  api key  NOT FOUND -> every scan will fall back to rules-only.")
        print("           set ANTHROPIC_API_KEY, or save the key to:")
        print("           %s" % KEY_HOME)
    print("  " + "-" * 44)
    print("  open     http://localhost:%d/lfs.html" % PORT)
    print("  stop     Ctrl+C")
    print("  check    python dev-server.py --check-key")
    print("  measure  python dev-server.py --test <folder-of-pdfs>\n")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")


if __name__ == "__main__":
    main()
