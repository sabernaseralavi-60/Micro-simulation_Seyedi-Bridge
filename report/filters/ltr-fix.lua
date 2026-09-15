-- fa-only PDF filter: fixes two real bidi/xepersian rendering bugs found by
-- diffing the rendered PDF's own word coordinates against the source .qmd
-- (not guessed) — see PERSIAN-TYPESETTING-RECIPE.md §7.2 for the underlying
-- mechanism, this is a project-local, simplified port of that recipe's
-- ltr-code.lua (no is_fa/Meta gate needed: this filter is wired only into
-- _quarto-fa.yml's own pdf format, never loaded for report-en.qmd).
--
-- Bug 1 (Code): an inline code span containing a space and/or a decimal
-- point (e.g. `--lateral-resolution 0.8`) renders with its word order AND
-- its own decimal point reversed ("8 .0 -lateral-resolution-") when left as
-- plain pandoc-emitted \texttt{...} sitting in RTL prose flow.
-- Bug 2 (Inlines): a run of >=2 Latin words typed directly into Persian
-- prose with no special markup (e.g. "RCUT (Restricted Crossing U-Turn)")
-- renders with its word order reversed, while each word's own letters stay
-- correctly spelled.
--
-- Fix for both: wrap the run in xepersian's \lr{...} (NOT bidi's bare
-- \LR{...}, which fixes word order but mirrors the parenthesis GLYPHS
-- themselves — confirmed in the recipe this filter is ported from).

local function Code(el)
  if not FORMAT:match("latex") then return nil end
  local escaped = el.text:gsub("\\", "\\textbackslash{}")
  escaped = escaped:gsub("([%%&#_{}$])", "\\%1")
  return pandoc.RawInline("latex", "\\lr{\\texttt{" .. escaped .. "}}")
end

local ARABIC_PUNCT = { [0x060C] = true, [0x061B] = true, [0x061F] = true, [0x066A] = true }
local function is_arabic_script(s)
  for _, cp in utf8.codes(s) do
    if not ARABIC_PUNCT[cp] and (
      (cp >= 0x0600 and cp <= 0x06FF) or (cp >= 0xFB50 and cp <= 0xFDFF)
      or (cp >= 0xFE70 and cp <= 0xFEFF)
    ) then
      return true
    end
  end
  return false
end

-- A token joins the run if it has a Latin letter OR an ASCII digit (and no
-- Persian letter/digit) — digits join too so a "Webster 1958"-style run
-- gets its order fixed, not just plain-letter runs.
local function is_run_member(s)
  return (s:find("%a") ~= nil or s:find("%d") ~= nil) and not is_arabic_script(s)
end

-- Persian punctuation (، ؛ ؟ ٪) attached to a Latin word with no space
-- (correct Persian style, e.g. "SUMO،") is split off the token's end rather
-- than disqualifying the whole token or being pulled into the \lr{} box.
local function split_trailing_arabic_punct(s)
  local cps = {}
  for _, cp in utf8.codes(s) do cps[#cps + 1] = cp end
  local n = #cps
  local split_at = n + 1
  for i = n, 1, -1 do
    if ARABIC_PUNCT[cps[i]] then split_at = i else break end
  end
  if split_at > n then return s, "" end
  local function join(from, to)
    if from > to then return "" end
    local chars = {}
    for i = from, to do chars[#chars + 1] = utf8.char(cps[i]) end
    return table.concat(chars)
  end
  return join(1, split_at - 1), join(split_at, n)
end

local function wrap_latin_runs(inlines)
  local out = pandoc.List()
  local run, run_words = pandoc.List(), 0
  local pending = pandoc.List()

  local function flush_run()
    if run_words >= 2 then
      out:insert(pandoc.RawInline("latex", "\\lr{"))
      for _, el in ipairs(run) do out:insert(el) end
      out:insert(pandoc.RawInline("latex", "}"))
    else
      for _, el in ipairs(run) do out:insert(el) end
    end
    run, run_words = pandoc.List(), 0
  end

  local function flush_all()
    flush_run()
    for _, sp in ipairs(pending) do out:insert(sp) end
    pending = pandoc.List()
  end

  for _, el in ipairs(inlines) do
    if el.t == "Str" then
      local latin_part, punct_part = split_trailing_arabic_punct(el.text)
      if latin_part ~= "" and is_run_member(latin_part) then
        for _, sp in ipairs(pending) do run:insert(sp) end
        pending = pandoc.List()
        run:insert(pandoc.Str(latin_part))
        run_words = run_words + 1
        if punct_part ~= "" then
          flush_run()
          out:insert(pandoc.Str(punct_part))
        end
      else
        flush_all()
        out:insert(el)
      end
    elseif (el.t == "Space" or el.t == "SoftBreak") and run_words > 0 then
      -- SoftBreak = a plain line-wrap inside one source paragraph (common
      -- in this project's ~80-column-wrapped .qmd prose); must join a run
      -- exactly like Space, or a Latin phrase that happens to wrap across
      -- two source lines gets split into two separately-ordered \lr{}
      -- groups instead of one.
      pending:insert(pandoc.Space())
    else
      flush_all()
      out:insert(el)
    end
  end
  flush_all()
  return out
end

local function Inlines(inlines)
  if not FORMAT:match("latex") then return nil end
  return wrap_latin_runs(inlines)
end

-- Two ordered passes (Code first, alone) so a Code element's own raw-LaTeX
-- replacement is never re-walked by the Inlines pass afterward.
return { { Code = Code }, { Inlines = Inlines } }
