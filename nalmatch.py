#!/usr/bin/env python
"""Reconcile a GIS parcel layer against the tax roll and name every parcel that exists on one side only.

Refuses any identifier rule that would merge two parcels into one key.

A join between a parcel layer and a Department of Revenue roll extract is one
line of SQL and it always succeeds. Succeeding is the problem. It matches the
rows whose identifiers happen to agree and says nothing about the rows it did
not match, so a subdivision that dropped out of the join looks exactly like a
subdivision that was never there.

The obvious tool is the join itself: arcpy.AddJoin_management, a pandas merge,
or a LEFT JOIN in the database. All three do the matching correctly and quickly,
and a pandas merge with indicator=True will even tell you which side each row
came from. None of them has an opinion about the key. If the two sides spell the
parcel identifier differently, every one of them reports a clean join over the
subset that agreed. The gap is the identifier rule, not the join.

This tool normalises the identifier on each side, reports the four classes that
do not reconcile, and refuses outright when the normalisation it was asked for
would give two distinct parcels the same key.

    python nalmatch.py --self-test
    python nalmatch.py parcels.csv nal.csv
    python nalmatch.py parcels.csv nal.csv --gis-id-field PARCELNO
    python nalmatch.py parcels.csv nal.csv --profile generic --punctuation strip
    python nalmatch.py parcels.csv nal.csv --write-csv exceptions.csv --apply

Nothing is written without --apply.

Exit codes: 0 everything reconciles, 1 something did not reconcile, 2 a file
could not be read, 3 the identifier rule was refused, 64 usage error.
"""

from __future__ import print_function

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile

# =============================================================================
# CONFIGURATION. Deliberately not flags. Change here, not at the call site.
# =============================================================================

# The profile used when --profile is not given. This tool was written for
# Florida county work, so the Florida rule is the default and "generic" is the
# one you ask for.
DEFAULT_PROFILE = "florida-nal"

# The column both sides are read from when --gis-id-field and --roll-id-field
# are not given. PARCEL_ID is the identifier column in the Department of
# Revenue NAL extract. A GIS layer rarely agrees, which is why both are flags.
DEFAULT_ID_FIELD = "PARCEL_ID"

# How many records are listed under each class. The count is the finding; the
# sample is there so somebody can open one record and agree.
DEFAULT_SAMPLE = 10

# Characters treated as separators when punctuation is stripped. These are the
# ones that appear between the strip, township, range, section, block and lot
# parts of a parcel identifier. No backslash: a parcel identifier does not
# carry one, and a file that does is not carrying parcel identifiers.
PUNCTUATION = "-. _/"

# =============================================================================
# End of CONFIGURATION.
# =============================================================================

# Why one identifier could not be used at all. None of these is a match
# failure: they are values this tool declines to turn into a key.
BLANK = "blank"
NOT_TEXT = "not-text"
NON_ASCII = "non-ascii"
PUNCT_ONLY = "punctuation-only"
TOO_LONG = "too-long"
TOO_SHORT = "too-short"

REASON_TEXT = {
    BLANK: "empty once trimmed, so there is no identifier to match on",
    NOT_TEXT: "arrived as a number rather than as text, so any leading zero it "
              "once had is already gone",
    NON_ASCII: "holds a character outside ASCII, which this profile will not "
               "fold into an ASCII key",
    PUNCT_ONLY: "nothing left after the separators were removed",
    TOO_LONG: "longer than this profile allows, so it belongs to a different "
              "identifier scheme",
    TOO_SHORT: "too short to carry a check digit",
}

DIGITS = "0123456789"

# Verdicts.
RECONCILES = "RECONCILES"
DOES_NOT = "DOES NOT RECONCILE"
REFUSED = "REFUSED"


def is_digits(text):
    """True for an ASCII number, and only for one.

    str.isdigit() is True for a full width digit and for a superscript two, and
    both of those would then be zero padded with ASCII zeros into a key nobody
    typed. A parcel identifier is an ASCII number or it is not a number.
    """
    return bool(text) and all(c in DIGITS for c in text)


class Rules(object):
    """One identifier rule: what is done to a raw value to make a key."""

    def __init__(self, name, fold_case=True, strip_punctuation=False,
                 pad_to=None, strip_check_digit=False, max_len=0,
                 ascii_only=False):
        # pad_to is the one field with three states, because padding has three
        # useful settings: off, "as wide as the widest number in these two
        # files", and an exact width somebody knows.
        self.name = name
        self.fold_case = fold_case
        self.strip_punctuation = strip_punctuation
        self.pad_to = pad_to
        self.strip_check_digit = strip_check_digit
        self.max_len = max_len
        self.ascii_only = ascii_only

    def replace(self, **kw):
        """A copy with some fields changed. One flag overrides one rule."""
        fields = {"name": self.name, "fold_case": self.fold_case,
                  "strip_punctuation": self.strip_punctuation,
                  "pad_to": self.pad_to,
                  "strip_check_digit": self.strip_check_digit,
                  "max_len": self.max_len, "ascii_only": self.ascii_only}
        for key in kw:
            if key not in fields:
                raise ValueError("no such rule %r" % (key,))
            fields[key] = kw[key]
        return Rules(**fields)

    def __repr__(self):
        return "Rules(%s)" % self.name


def profiles():
    """A fresh copy of the shipped profiles, so a caller cannot edit them."""
    return {
        # Florida county work. Punctuation varies between the roll extract and
        # the layer, the roll arrives from a spreadsheet often enough that
        # padding is on, and an identifier from another state's scheme is
        # refused rather than folded into the county keyspace.
        "florida-nal": Rules(
            "florida-nal", fold_case=True, strip_punctuation=True,
            pad_to=0, strip_check_digit=False, max_len=18, ascii_only=True),
        # The least a rule can do: trim and fold case. Everything that could
        # merge two parcels has to be asked for by name.
        "generic": Rules(
            "generic", fold_case=True, strip_punctuation=False,
            pad_to=None, strip_check_digit=False, max_len=0,
            ascii_only=False),
    }


class Entry(object):
    """One raw identifier, and either the key it makes or why it makes none."""

    def __init__(self, raw, key, reason):
        self.raw = raw
        self.key = key
        self.reason = reason

    @property
    def ok(self):
        return self.reason is None

    @property
    def shown(self):
        """The raw value as it should be printed, never as a bare None."""
        return "" if self.raw is None else str(self.raw)

    def __repr__(self):
        return "Entry(%r, %r)" % (self.shown, self.key or self.reason)


class Repeat(object):
    """One key that more than one record on one side claims."""

    def __init__(self, side, key, raws):
        self.side = side
        self.key = key
        self.raws = list(raws)

    def __repr__(self):
        return "Repeat(%s, %s, %d)" % (self.side, self.key, len(self.raws))


class Result(object):
    """What the two sides prove about each other under one rule."""

    def __init__(self, rules, width, gis, roll, collisions, duplicates,
                 gis_only, roll_only, matched):
        self.rules = rules
        self.width = width
        self.gis = gis
        self.roll = roll
        self.collisions = collisions
        self.duplicates = duplicates
        self.gis_only = gis_only
        self.roll_only = roll_only
        self.matched = matched

    @property
    def rejected(self):
        return [e for e in self.gis if not e.ok] + \
               [e for e in self.roll if not e.ok]

    @property
    def refused(self):
        """A rule that merges two parcels is refused, not reported."""
        return bool(self.collisions)

    @property
    def verdict(self):
        if self.refused:
            return REFUSED
        if self.gis_only or self.roll_only or self.duplicates or self.rejected:
            return DOES_NOT
        return RECONCILES

    def __repr__(self):
        return "Result(%s, %d matched)" % (self.verdict, self.matched)


# ----------------------------------------------------------------- pure core

def normalise(raw, rules, width=0):
    """(key, reason) for one raw identifier. The key is None when refused.

    The order of the steps is the product. Punctuation goes before the length
    ceiling, so that a dashed identifier is measured by its digits. The ceiling
    goes before the check digit, so that an identifier from another scheme is
    named as out of profile instead of being trimmed into this one. Padding
    goes last, so that a value this rule refused can never set the width the
    rest of the file is padded to.
    """
    if raw is None:
        return None, BLANK
    if not isinstance(raw, str):
        # csv gives text for every cell. A number here came from a reader that
        # already parsed it, which is the moment the leading zeros were lost,
        # and padding a guess back on would be inventing an identifier.
        return None, NOT_TEXT
    text = raw.strip()
    if not text:
        return None, BLANK
    if rules.ascii_only:
        try:
            text.encode("ascii")
        except UnicodeEncodeError:
            return None, NON_ASCII
    key = text.upper() if rules.fold_case else text
    if rules.strip_punctuation:
        key = "".join(c for c in key if c not in PUNCTUATION)
        if not key:
            return None, PUNCT_ONLY
    if rules.max_len and len(key) > rules.max_len:
        return None, TOO_LONG
    if rules.strip_check_digit:
        if len(key) < 2:
            return None, TOO_SHORT
        key = key[:-1]
    if width and is_digits(key) and len(key) < width:
        key = key.zfill(width)
    return key, None


def prepare(raws, rules, width=0):
    """Every raw identifier on one side, as entries, in file order."""
    if not isinstance(raws, list):
        raise ValueError("expected a list of identifiers, got %r"
                         % (type(raws),))
    if rules is None:
        raise ValueError("a rule is required")
    out = []
    for raw in raws:
        key, reason = normalise(raw, rules, width)
        out.append(Entry(raw, key, reason))
    return out


def pad_width(*groups):
    """The width to pad to: the widest usable all-digit key in these groups.

    Only keys this rule accepted are measured. An identifier the profile
    refused is from another scheme, and letting it set the width would pad
    every parcel in the county to a length nothing else has.
    """
    width = 0
    for entries in groups:
        for entry in entries:
            if entry.ok and is_digits(entry.key):
                width = max(width, len(entry.key))
    return width


def group_keys(entries):
    """key -> the entries claiming it, for the entries that made a key."""
    out = {}
    for entry in entries:
        if entry.ok:
            out.setdefault(entry.key, []).append(entry)
    return out


def split_repeats(entries, side):
    """(duplicates, collisions) for one side.

    A duplicate is the same identifier written twice: a repeated row, and the
    join would return it twice. A collision is two identifiers that were
    different until this rule made them the same, and the join would return one
    parcel wearing the other's roll record. They are printed apart because only
    one of them is a reason to stop.
    """
    duplicates = []
    collisions = []
    for key, group in group_keys(entries).items():
        if len(group) < 2:
            continue
        distinct = []
        for entry in group:
            text = entry.shown.strip()
            if text not in distinct:
                distinct.append(text)
        if len(distinct) == 1:
            duplicates.append(Repeat(side, key, [distinct[0]] * len(group)))
        else:
            collisions.append(Repeat(side, key, distinct))
    return duplicates, collisions


def reconcile(gis_raws, roll_raws, rules):
    """Both sides under one rule: what matched, what did not, what is refused.

    Two passes when padding is on. The first pass makes the keys, the second
    pads them, and the width can only be known once the first pass has said
    which identifiers this profile accepts at all.

    The rule and both sides are validated by prepare() below, which is reached
    before anything here reads either one.
    """
    gis = prepare(gis_raws, rules)
    roll = prepare(roll_raws, rules)
    width = 0
    if rules.pad_to is not None:
        width = rules.pad_to or pad_width(gis, roll)
        if width:
            gis = prepare(gis_raws, rules, width)
            roll = prepare(roll_raws, rules, width)

    gis_dupes, gis_collisions = split_repeats(gis, "gis")
    roll_dupes, roll_collisions = split_repeats(roll, "roll")

    gis_keys = set(e.key for e in gis if e.ok)
    roll_keys = set(e.key for e in roll if e.ok)
    gis_only = [e for e in gis if e.ok and e.key not in roll_keys]
    roll_only = [e for e in roll if e.ok and e.key not in gis_keys]

    return Result(rules, width, gis, roll,
                  gis_collisions + roll_collisions,
                  gis_dupes + roll_dupes,
                  gis_only, roll_only,
                  len(gis_keys & roll_keys))


def rule_summary(rules, width=0):
    """The rule as one line, so a report says what it did to the keys."""
    parts = ["profile %s" % rules.name]
    parts.append("fold case" if rules.fold_case else "keep case")
    parts.append("strip punctuation" if rules.strip_punctuation
                 else "keep punctuation")
    if rules.pad_to is None:
        parts.append("no padding")
    elif width:
        parts.append("pad numbers to %d" % width)
    else:
        parts.append("pad numbers to the widest (nothing to pad)")
    if rules.strip_check_digit:
        parts.append("drop the last character")
    if rules.max_len:
        parts.append("ceiling %d characters" % rules.max_len)
    parts.append("reject non-ASCII" if rules.ascii_only else "allow non-ASCII")
    return ", ".join(parts)


def exceptions(result):
    """Every record that did not reconcile, as rows for a CSV or a report.

    One shape for all four classes, because the person reading it wants one
    list to work through and not four.
    """
    rows = []
    for rep in result.collisions:
        for raw in rep.raws:
            rows.append((rep.side, "collision", raw, rep.key,
                         "this rule gives it the same key as %d other "
                         "identifier(s) on this side" % (len(rep.raws) - 1)))
    if result.refused:
        # Every other class was computed under a rule that merges parcels, so
        # the collisions are the whole answer here as well.
        return rows
    for rep in result.duplicates:
        for raw in rep.raws:
            rows.append((rep.side, "duplicate", raw, rep.key,
                         "written %d times on this side" % len(rep.raws)))
    for entry in result.gis_only:
        rows.append(("gis", "no-roll-record", entry.shown, entry.key,
                     "no roll record carries this key"))
    for entry in result.roll_only:
        rows.append(("roll", "no-parcel", entry.shown, entry.key,
                     "no parcel carries this key"))
    for side, entries in (("gis", result.gis), ("roll", result.roll)):
        for entry in entries:
            if not entry.ok:
                rows.append((side, "rejected", entry.shown, "",
                             REASON_TEXT[entry.reason]))
    return rows


def describe(result, sample=DEFAULT_SAMPLE):
    """The lines the CLI prints.

    A refusal prints the collisions and stops. Printing a reconciliation under
    a rule that merges two parcels would be publishing a number this tool
    already knows is wrong.
    """
    if sample < 0:
        raise ValueError("sample cannot be negative")
    lines = ["KEY RULE  %s" % rule_summary(result.rules, result.width)]
    if result.refused:
        merged = sum(len(r.raws) for r in result.collisions)
        lines.append("REFUSED   this rule gives %d distinct identifier(s) "
                     "%d shared key(s)" % (merged, len(result.collisions)))
        for rep in result.collisions[:sample]:
            lines.append("      %s key %s is claimed by:" % (rep.side, rep.key))
            for raw in rep.raws:
                lines.append("          %s" % raw)
        if len(result.collisions) > sample:
            lines.append("      ... %d more"
                         % (len(result.collisions) - sample))
        lines.append("      nothing is reported against a rule that merges "
                     "parcels. Change the rule or fix the identifiers.")
        lines.append("VERDICT: %s" % REFUSED)
        return lines

    lines.append("MATCHED   %d key(s) on both sides" % result.matched)

    def listing(head, entries, render):
        lines.append(head)
        for item in entries[:sample]:
            lines.append("      %s" % render(item))
        if len(entries) > sample:
            lines.append("      ... %d more" % (len(entries) - sample))

    listing("GIS ONLY  %d parcel(s) with no roll record" % len(result.gis_only),
            result.gis_only, lambda e: "%s  ->  %s" % (e.shown, e.key))
    listing("ROLL ONLY %d roll record(s) with no parcel" % len(result.roll_only),
            result.roll_only, lambda e: "%s  ->  %s" % (e.shown, e.key))
    listing("DUPLICATE %d key(s) written more than once"
            % len(result.duplicates), result.duplicates,
            lambda r: "%s %s written %d times"
                      % (r.side, r.raws[0], len(r.raws)))
    rejected = result.rejected
    listing("REJECTED  %d identifier(s) this profile will not use"
            % len(rejected), rejected,
            lambda e: "%s  ->  %s" % (e.shown or "(empty)",
                                      REASON_TEXT[e.reason]))
    lines.append("VERDICT: %s" % result.verdict)
    return lines


def as_json(result, sample=DEFAULT_SAMPLE):
    """The same content as describe(), shaped for a script."""
    if sample < 0:
        raise ValueError("sample cannot be negative")
    doc = {
        "verdict": result.verdict,
        "profile": result.rules.name,
        "rule": rule_summary(result.rules, result.width),
        "pad_width": result.width,
        "gis_records": len(result.gis),
        "roll_records": len(result.roll),
        "matched": result.matched,
        "collisions": [{"side": r.side, "key": r.key, "identifiers": r.raws}
                       for r in result.collisions],
        "duplicates": [],
        "gis_only": [],
        "roll_only": [],
        "rejected": [],
    }
    if result.refused:
        # Counts computed under a merging rule are not published. The
        # collisions above are the whole answer.
        return doc
    doc["duplicates"] = [{"side": r.side, "key": r.key, "count": len(r.raws),
                          "identifier": r.raws[0]}
                         for r in result.duplicates[:sample]]
    doc["gis_only"] = [{"identifier": e.shown, "key": e.key}
                       for e in result.gis_only[:sample]]
    doc["roll_only"] = [{"identifier": e.shown, "key": e.key}
                        for e in result.roll_only[:sample]]
    doc["rejected"] = [{"identifier": e.shown, "reason": e.reason,
                        "detail": REASON_TEXT[e.reason]}
                       for e in result.rejected[:sample]]
    doc["counts"] = {"duplicates": len(result.duplicates),
                     "gis_only": len(result.gis_only),
                     "roll_only": len(result.roll_only),
                     "rejected": len(result.rejected)}
    return doc


# ------------------------------------------------------------------------ io

def read_csv_rows(path):
    """(field names, rows) from a CSV.

    utf-8-sig, because a CSV written by Excel opens with a byte order mark and
    reading it as plain utf-8 names the first field PARCEL_ID with an invisible
    character in front of it, which then matches no --gis-id-field anybody
    types.
    """
    with open(path, "r", newline="", encoding="utf-8-sig",
              errors="replace") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    if not fields:
        raise ValueError("%s has no header row" % path)
    return fields, rows


def column(rows, field):
    """Every cell of one field, blanks and all, in row order."""
    return [row.get(field) for row in rows]


def write_exceptions(path, result):
    """Write the exception rows as a CSV. Returns how many were written."""
    rows = exceptions(result)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["SIDE", "CLASS", "IDENTIFIER", "KEY", "DETAIL"])
        for row in rows:
            writer.writerow(list(row))
    return len(rows)


def build_rules(args):
    """The rule this run uses: a profile, then one flag per overridden rule."""
    available = profiles()
    if args.profile not in available:
        raise ValueError("unknown profile %r. Available: %s"
                         % (args.profile, ", ".join(sorted(available))))
    rules = available[args.profile]
    if args.case is not None:
        rules = rules.replace(fold_case=args.case == "fold")
    if args.punctuation is not None:
        rules = rules.replace(strip_punctuation=args.punctuation == "strip")
    if args.pad is not None:
        if args.pad == "off":
            rules = rules.replace(pad_to=None)
        elif args.pad == "auto":
            rules = rules.replace(pad_to=0)
        else:
            if not is_digits(args.pad) or int(args.pad) < 1:
                raise ValueError("--pad takes auto, off, or a width of at "
                                 "least 1, not %r" % (args.pad,))
            rules = rules.replace(pad_to=int(args.pad))
    if args.check_digit is not None:
        rules = rules.replace(strip_check_digit=args.check_digit == "strip")
    if args.max_len is not None:
        if args.max_len < 0:
            raise ValueError("--max-len cannot be negative. 0 means no ceiling.")
        rules = rules.replace(max_len=args.max_len)
    if args.non_ascii is not None:
        rules = rules.replace(ascii_only=args.non_ascii == "reject")
    return rules


# ------------------------------------------------------------------ self-test

def self_test():
    """Assertions over the decision core, then over the io layer.

    Nothing here reaches the network, a database or arcpy. The io half writes
    CSV fixtures into a temporary directory and runs main() over them, because
    a reader that has never read a file has not been tested.
    """
    passed = [0]
    failed = []

    def check(cond, label):
        if cond:
            passed[0] += 1
            print("PASS  %s" % label)
        else:
            failed.append(label)
            print("FAIL  %s" % label)

    def raises(fn, label):
        try:
            fn()
        except ValueError:
            check(True, label)
        except Exception as exc:
            check(False, "%s (wrong exception %r)" % (label, exc))
        else:
            check(False, "%s (no error raised)" % label)

    print("nalmatch self-test: no network, no database, a temporary directory "
          "for the io layer")
    print("-" * 68)

    fl = profiles()["florida-nal"]
    generic = profiles()["generic"]

    def key_of(raw, rules=fl, width=0):
        return normalise(raw, rules, width)[0]

    def reason_of(raw, rules=fl, width=0):
        return normalise(raw, rules, width)[1]

    def matched(gis, roll, rules=fl):
        return reconcile(gis, roll, rules).matched

    # ---- the shipped profiles
    # Each configured constant is pinned to its literal here. An assertion
    # that only compares a parsed default against the constant that set it
    # would pass whatever the constant was changed to.
    check(DEFAULT_PROFILE == "florida-nal",
          "the default profile is the Florida one, which is what every "
          "assertion below is written against")
    check(DEFAULT_ID_FIELD == "PARCEL_ID",
          "the default column is the one the Department of Revenue extract "
          "uses  <-- pinned defect")
    check(DEFAULT_SAMPLE == 10,
          "ten records are listed under each class by default  "
          "<-- pinned defect")
    check(sorted(profiles()) == ["florida-nal", "generic"],
          "two profiles ship")
    check(fl.strip_punctuation and fl.fold_case and fl.ascii_only,
          "florida-nal folds case, strips punctuation and refuses non-ASCII")
    check(fl.pad_to == 0, "and pads numbers to the widest one it was given")
    check(fl.max_len == 18, "with an 18 character ceiling")
    check(fl.strip_check_digit is False,
          "check digit stripping is OFF by default: it deletes a character "
          "from every identifier  <-- pinned defect")
    check(generic.fold_case is True,
          "generic folds case, because a lower case identifier is the same "
          "identifier")
    check(generic.strip_punctuation is False and generic.pad_to is None
          and generic.max_len == 0 and generic.ascii_only is False,
          "and does NOTHING else: every rule that can merge two parcels has "
          "to be asked for  <-- pinned defect")
    check(profiles()["florida-nal"] is not fl,
          "profiles() hands back a fresh copy, so one run cannot edit the "
          "rule another run gets")
    check(fl.replace(max_len=0).max_len == 0 and fl.max_len == 18,
          "replace() copies rather than editing in place")
    check(repr(fl) == "Rules(florida-nal)", "a rule reprs as its name")
    raises(lambda: fl.replace(strip_leading_zeros=True),
           "replacing a rule that does not exist raises rather than being "
           "silently ignored  <-- pinned defect")

    # ---- THE TABLE. One row per identifier pair, read under florida-nal.
    #
    # The third column is whether the two sides reconcile to one key. Every
    # normalisation rule has a row that needs it and a row that must not be
    # matched by it.
    pairs = [
        ("12345-001-000", "12345-001-000", True,
         "an identical pair matches"),
        ("12345-001-000", "12345001000", True,
         "punctuation on one side only still matches"),
        ("12345.001.000", "12345-001-000", True,
         "a dot and a dash are the same separator"),
        ("12345 001 000", "12345001000", True,
         "a space inside the identifier is a separator too"),
        ("12345_001_000", "12345001000", True,
         "and an underscore"),
        ("12345/001/000", "12345001000", True,
         "and a slash"),
        ("  12345001000  ", "12345001000", True,
         "surrounding whitespace is trimmed"),
        ("\t12345001000\n", "12345001000", True,
         "and so are a tab and a newline"),
        ("r12345001000", "R12345001000", True,
         "case is folded, so a lower case prefix matches an upper case one"),
        ("R12345001000", "R-12345-001-000", True,
         "a lettered identifier survives punctuation stripping"),
        ("00123001000", "123001000", True,
         "the roll identifier that lost its leading zeros in a spreadsheet "
         "still matches  <-- pinned defect"),
        ("00123-001-000", "123001000", True,
         "punctuation and lost leading zeros together, which is the join in "
         "the story  <-- pinned defect"),
        ("00000000001", "1", True,
         "ten lost zeros are still recovered, because the width comes from "
         "the other side"),
        ("12345001000", "12345001001", False,
         "two genuinely different parcels do not match"),
        ("12345001000", "1234500100", False,
         "an identifier one digit short does not match: padding makes it "
         "01234500100, not the original  <-- pinned defect"),
        ("1000", "0100", False,
         "two numbers of the same width are never brought together by "
         "padding  <-- pinned defect"),
        ("12345001000", "", False,
         "a blank roll identifier matches nothing"),
        ("12345001000", "   ", False,
         "and neither does a whitespace-only one  <-- pinned defect"),
        ("12345001000", "---", False,
         "nor one that is only separators  <-- pinned defect"),
        ("12345001000", None, False,
         "nor a missing cell"),
        ("12345001000", "1234567890123456789", False,
         "nor a 19 digit identifier from another county's scheme, which is "
         "rejected rather than truncated  <-- pinned defect"),
        ("1234567890123456789", "1234567890123456789", False,
         "and the same 19 digit identifier on BOTH sides still does not "
         "match, because neither side made a key  <-- pinned defect"),
        ("123456789012345678", "123456789012345678", True,
         "18 characters is inside the ceiling and matches"),
        ("12345-001-000", "12345-001-000-X", False,
         "a trailing check digit is NOT stripped by default, so it does not "
         "match  <-- pinned defect"),
        ("12345001000", "12345001000 ", True,
         "a trailing space is not a difference"),
        ("PARCEL 12345001000", "PARCEL12345001000", True,
         "a word in the identifier is kept, only the separators go"),
        ("12345001000", "12345001OOO", False,
         "letter O typed for digit zero does not match, and is not guessed "
         "at  <-- pinned defect"),
        (u"12345\u2013001\u2013000", "12345001000", False,
         "an en dash is not a hyphen: the profile refuses it as non-ASCII "
         "rather than treating it as a separator  <-- pinned defect"),
        (u"\uff11\uff12\uff13", "123", False,
         "full width digits are refused, not folded into ASCII ones  "
         "<-- pinned defect"),
        ("12345001000", "12345001000", True,
         "and the plain pair matches, so the table is not all refusals"),
    ]
    check(len(pairs) >= 30, "the table covers at least thirty identifier pairs")
    for gis, roll, should, label in pairs:
        check((matched([gis], [roll]) == 1) is should, label)

    # ---- one rule at a time, each with a case that needs it and a case that
    # must not be caught by it.
    check(key_of("abc-123") == "ABC123", "the florida rule makes one key")
    check(key_of("abc-123", fl.replace(fold_case=False)) == "abc123",
          "keep case leaves the letters alone")
    check(key_of("abc-123", generic) == "ABC-123",
          "generic folds the case and keeps the punctuation")
    check(key_of("abc-123", generic.replace(strip_punctuation=True))
          == "ABC123", "and strips it when asked")
    check(key_of("  abc  ", generic) == "ABC",
          "generic still trims, because trailing whitespace is never part of "
          "an identifier")
    check(key_of("00042", fl, width=8) == "00000042",
          "an explicit width pads a number")
    check(key_of("42", fl, width=8) == "00000042",
          "to the same key from either spelling")
    check(key_of("000000042", fl, width=8) == "000000042",
          "a number already wider than the width is left alone, never cut  "
          "<-- pinned defect")
    check(key_of("A42", fl, width=8) == "A42",
          "a key with a letter in it is NOT padded: a lettered identifier is "
          "not a number with zeros missing  <-- pinned defect")
    check(key_of("42", fl, width=0) == "42", "a width of zero pads nothing")
    check(key_of("42", fl, width=25) == "00000000000000000000000" + "42",
          "an explicit width wider than the profile ceiling still pads to it: "
          "the ceiling measures the identifier that arrived, and padding is "
          "the repair applied after it  <-- pinned defect")
    check(len(key_of("42", fl, width=25)) == 25,
          "so the key really is 25 characters, not cut back to the 18 "
          "character ceiling  <-- pinned defect")

    # pad_width fed entries by hand, because the width it returns decides the
    # key every other record in the file is looked up by.
    check(pad_width([Entry("42", "42", None),
                     Entry("000042", "000042", None)]) == 6,
          "the width is the widest accepted number it was shown")
    check(pad_width([Entry("42", "42", None)], [Entry("0042", "0042", None)])
          == 4, "measured across every group it was given, not one at a time")
    check(pad_width([Entry("A4200", "A4200", None)]) == 0,
          "a key with a letter in it sets no width, because it is not a "
          "number with zeros missing  <-- pinned defect")
    check(pad_width([]) == 0 and pad_width() == 0,
          "and nothing at all is a width of zero")
    check(pad_width([Entry("1234567890123456789", "1234567890123456789",
                           TOO_LONG)]) == 0,
          "an entry that carries a key AND a refusal reason sets no width: "
          "pad_width trusts the reason, not the key  <-- pinned defect")
    check(key_of("12345678", fl.replace(strip_check_digit=True)) == "1234567",
          "check digit stripping drops the last character")
    check(key_of("1234567X", fl.replace(strip_check_digit=True)) == "1234567",
          "whatever that character is")
    check(reason_of("1", fl.replace(strip_check_digit=True)) == TOO_SHORT,
          "a one character identifier has no check digit to strip and is "
          "refused rather than emptied  <-- pinned defect")
    check(key_of("12", fl.replace(strip_check_digit=True)) == "1",
          "two characters is the shortest that can lose one")
    check(reason_of("1234567890123456789") == TOO_LONG,
          "19 characters is over the ceiling")
    check(key_of("1234567890123456789", fl.replace(max_len=0))
          == "1234567890123456789",
          "a ceiling of zero means no ceiling, and the key is the identifier "
          "whole  <-- pinned defect")
    check(key_of("1234567890123456789", generic)
          == "1234567890123456789",
          "and generic has none, so the same value is a key there")
    check(reason_of("1234-5678-9012-3456-789") == TOO_LONG,
          "the ceiling is measured after punctuation is removed, so a dashed "
          "19 digit identifier is refused too  <-- pinned defect")
    check(key_of("1234-5678-9012-3456-78") == "123456789012345678",
          "while 18 digits with the same dashes is accepted, and keys as "
          "those 18 digits  <-- pinned defect")
    check(reason_of("1234567890123456789",
                    fl.replace(strip_check_digit=True)) == TOO_LONG,
          "the ceiling is checked BEFORE the check digit is stripped, so a "
          "foreign identifier cannot be trimmed into profile  <-- pinned defect")
    check(reason_of(u"12345\u00d1") == NON_ASCII,
          "a non-ASCII character is refused by this profile")
    check(key_of(u"12345\u00d1", fl.replace(ascii_only=False))
          == u"12345\u00d1",
          "and kept verbatim when the profile allows it, never transliterated"
          "  <-- pinned defect")
    check(key_of(u"12345\u00f1", fl.replace(ascii_only=False))
          == u"12345\u00d1",
          "case folding still applies to it")
    check(reason_of(u"\uff11\uff12\uff13") == NON_ASCII,
          "full width digits are non-ASCII, whatever str.isdigit says about "
          "them  <-- pinned defect")
    check(u"\uff11\uff12\uff13".isdigit() is True,
          "and str.isdigit really does say they are digits, which is the trap")
    check(is_digits(u"\uff11\uff12\uff13") is False,
          "so this tool asks a different question")
    check(is_digits("123") is True and is_digits("12A") is False
          and is_digits("") is False,
          "which is answered only by ASCII 0 to 9")
    check(is_digits(u"\u00b2") is False and u"\u00b2".isdigit() is True,
          "a superscript two is not a number here either  <-- pinned defect")
    check(key_of(u"\uff11\uff12\uff13", generic, width=6)
          == u"\uff11\uff12\uff13",
          "and it is not padded with ASCII zeros")

    # ---- what makes no key at all
    check(reason_of(None) == BLANK, "a missing cell makes no key")
    check(reason_of("") == BLANK, "an empty string makes no key")
    check(reason_of("   ") == BLANK, "a whitespace-only cell makes no key")
    check(reason_of("\t\n") == BLANK, "whitespace means any whitespace")
    check(reason_of("---") == PUNCT_ONLY,
          "an identifier of separators makes no key, and says which of the "
          "two empties it was")
    check(reason_of("- . _ /") == PUNCT_ONLY, "every separator, likewise")
    check(reason_of("---", generic) is None and key_of("---", generic) == "---",
          "while generic keeps it, because generic strips no punctuation")
    check(reason_of(12345) == NOT_TEXT,
          "an identifier that arrived as an int is refused: the leading zeros "
          "are already gone and padding would invent them  <-- pinned defect")
    check(reason_of(12345.0) == NOT_TEXT, "and as a float")
    check(reason_of(True) == NOT_TEXT, "and as a bool")
    check(reason_of(float("nan")) == NOT_TEXT,
          "a NaN is refused as a number rather than compared, because NaN is "
          "not equal to itself and would match nothing  <-- pinned defect")
    check(reason_of(b"12345") == NOT_TEXT,
          "and so are bytes, which is a file opened in binary by mistake")
    check(reason_of(["12345"]) == NOT_TEXT, "and a list")
    check(reason_of("9" * 1000000) == TOO_LONG,
          "a one million character cell is refused by the ceiling rather "
          "than padded, sliced or crashed on  <-- pinned defect")
    check(len(key_of("9" * 1000000, generic)) == 1000000,
          "while generic, which has no ceiling, keys it whole")
    check(key_of(u"12345\u00a0") == "12345",
          "a trailing non-breaking space is trimmed like any other "
          "whitespace, so it never reaches the ASCII test  <-- pinned defect")
    check(reason_of(u"12345\u00a0X") == NON_ASCII,
          "while one in the middle of an identifier is not whitespace to "
          "trim, and the profile refuses it  <-- pinned defect")
    check(reason_of(u"12345\U0001f600") == NON_ASCII, "an emoji is refused")
    check(reason_of(u"12345\ud800") == NON_ASCII,
          "and so is a lone surrogate, rather than raising on the encode  "
          "<-- pinned defect")
    check(sorted(REASON_TEXT) == sorted([BLANK, NOT_TEXT, NON_ASCII,
                                         PUNCT_ONLY, TOO_LONG, TOO_SHORT]),
          "every refusal reason has a sentence explaining it")
    for reason in REASON_TEXT:
        check(len(REASON_TEXT[reason]) > 20,
              "the sentence for %s is a sentence" % reason)

    # ---- THE REFUSAL. A rule that merges two parcels stops the run.
    r = reconcile(["0123456", "123456"], ["0123456"], fl)
    check(r.refused is True,
          "two parcels that differ only by a leading zero make the padding "
          "rule REFUSE  <-- pinned defect")
    check(r.verdict == REFUSED, "and the verdict is REFUSED")
    check(len(r.collisions) == 1, "one key is contested")
    check(r.collisions[0].key == "0123456", "named as the key they share")
    check(sorted(r.collisions[0].raws) == ["0123456", "123456"],
          "and BOTH originals are named, because either one could be the "
          "parcel the roll meant  <-- pinned defect")
    check(r.collisions[0].side == "gis", "the side is named too")
    check(repr(r.collisions[0]) == "Repeat(gis, 0123456, 2)",
          "a collision reprs as its side, its key and its size")
    check(r.matched == 1,
          "a match count exists internally, and describe() refuses to print "
          "it  <-- pinned defect")
    lines = describe(r)
    check(any("REFUSED" in l for l in lines), "the report says REFUSED")
    check(not any(l.startswith("MATCHED") for l in lines),
          "and prints no match count under a merging rule  <-- pinned defect")
    check(not any(l.startswith("GIS ONLY") for l in lines),
          "nor any of the four classes, which would all be wrong  "
          "<-- pinned defect")
    check(any("0123456" in l for l in lines) and any("123456" in l
                                                     for l in lines),
          "it prints both originals instead")
    check(any("Change the rule" in l for l in lines),
          "and says what to do about it")
    doc = as_json(r)
    check(doc["verdict"] == REFUSED and len(doc["collisions"]) == 1,
          "the json carries the refusal")
    check(doc["collisions"][0]["identifiers"] == ["0123456", "123456"],
          "naming both identifiers in the order the file had them")
    check(doc["collisions"][0]["key"] == "0123456",
          "under the key this rule gave them both")
    check(doc["gis_only"] == [] and doc["roll_only"] == []
          and doc["duplicates"] == [] and "counts" not in doc,
          "and no reconciliation counts at all  <-- pinned defect")

    check(reconcile(["0123456", "123456"], [], fl.replace(pad_to=None)).refused
          is False,
          "with padding off the same two parcels keep different keys and "
          "nothing is refused  <-- pinned defect")
    check(reconcile(["0123456", "123456"], [],
                    fl.replace(pad_to=None)).matched == 0,
          "they simply both fail to match the roll")
    r = reconcile(["12-345", "12345"], [], fl)
    check(r.refused is True,
          "punctuation stripping can merge two parcels as well, and is "
          "refused the same way  <-- pinned defect")
    check(reconcile(["12-345", "12345"], [], generic).refused is False,
          "generic keeps them apart, which is what generic is for")
    r = reconcile(["1234567", "1234568"], [],
                  fl.replace(strip_check_digit=True))
    check(r.refused is True,
          "check digit stripping merges two parcels whose identifiers differ "
          "only in the last character  <-- pinned defect")
    check(sorted(r.collisions[0].raws) == ["1234567", "1234568"],
          "naming both")
    check(reconcile(["1234567", "1234568"], [], fl).refused is False,
          "while the same two are distinct parcels with the check digit "
          "kept, which is why stripping it is off by default")
    r = reconcile(["abc123", "ABC123"], [], fl)
    check(r.refused is True,
          "case folding merges two rows whose identifiers really did differ, "
          "and that is still a refusal  <-- pinned defect")
    check(reconcile(["abc123", "ABC123"], [],
                    fl.replace(fold_case=False)).refused is False,
          "keeping case leaves them apart")
    r = reconcile([], ["0123456", "123456"], fl)
    check(r.refused is True and r.collisions[0].side == "roll",
          "a collision on the ROLL side is refused too: the merge is just as "
          "wrong in that direction  <-- pinned defect")
    r = reconcile(["A", "B"], ["A", "B"], fl)
    check(r.refused is False, "distinct identifiers are not a collision")

    # ---- a duplicate is not a collision
    r = reconcile(["12345", "12345"], ["12345"], fl)
    check(r.refused is False,
          "the same identifier written twice is a duplicate, not a merge, so "
          "the run is not refused  <-- pinned defect")
    check(len(r.duplicates) == 1, "it is reported as one duplicate")
    check(r.duplicates[0].raws == ["12345", "12345"],
          "carrying the identifier twice")
    check(r.duplicates[0].side == "gis", "on the GIS side")
    check(r.verdict == DOES_NOT, "and the file does not reconcile")
    check(r.matched == 1, "although the key itself does match the roll")
    r = reconcile([" 12345 ", "12345"], [], fl)
    check(len(r.duplicates) == 1 and r.refused is False,
          "whitespace around one of them does not make it a different "
          "identifier  <-- pinned defect")
    r = reconcile(["12345", "12345", "12345"], [], fl)
    check(r.duplicates[0].raws == ["12345"] * 3, "three of them are counted")
    check(len(r.gis_only) == 3,
          "and all three are reported as having no roll record")

    # ---- the four classes on one pair of sides
    gis = ["00123-001-000", "00123-001-001", "00123-001-002", "00999-001-000"]
    roll = ["123001000", "123001001", "123001002", "00888001000"]
    r = reconcile(gis, roll, fl)
    check(r.refused is False, "the ordinary case is not refused")
    check(r.width == 11,
          "the padding width is the widest accepted number on either side")
    check(r.matched == 3, "three parcels reconcile")
    check([e.shown for e in r.gis_only] == ["00999-001-000"],
          "one parcel has no roll record")
    check([e.shown for e in r.roll_only] == ["00888001000"],
          "one roll record has no parcel")
    check(r.duplicates == [] and r.collisions == [], "nothing is repeated")
    check(r.verdict == DOES_NOT, "so the two sides do not reconcile")
    check(r.gis_only[0].key == "00999001000",
          "an unmatched parcel is reported with the key it was looked up by, "
          "so the reader can see what the rule did to it")
    check(repr(r) == "Result(DOES NOT RECONCILE, 3 matched)",
          "a result reprs as its verdict and its match count")
    check(repr(r.gis_only[0]) == "Entry('00999-001-000', '00999001000')",
          "an entry reprs as the identifier it arrived as and the key it made")
    check(repr(prepare([""], fl)[0]) == "Entry('', 'blank')",
          "and a refused one reprs as the reason it made none")

    # A missing cell arrives as None, and None must never reach a report or a
    # CSV as the four letters "None": that is an identifier nobody can look up.
    none_entry = prepare([None], fl)[0]
    check(none_entry.shown == "",
          "a missing cell shows as empty, never as the word None  "
          "<-- pinned defect")
    check(repr(none_entry) == "Entry('', 'blank')",
          "and reprs that way too")
    none_rows = exceptions(reconcile([None], [], fl))
    check(len(none_rows) == 1 and none_rows[0][2] == "",
          "so the exception row for it carries an empty identifier  "
          "<-- pinned defect")
    check("None" not in " ".join(describe(reconcile([None], [], fl))),
          "and the word None appears nowhere in the report  <-- pinned defect")
    check(as_json(reconcile([None], [], fl))["rejected"][0]["identifier"] == "",
          "the json says the same")
    check(reconcile(gis[:3], roll[:3], fl).verdict == RECONCILES,
          "and the same file without those two reconciles")
    check(reconcile(gis[:3], roll[:3], fl).matched == 3, "all three of them")

    # ---- the 312 lot subdivision from the story
    subdivision = ["0%s" % (49300000 + i) for i in range(312)]
    stripped = [str(int(p)) for p in subdivision]
    check(len(set(subdivision)) == 312, "312 distinct parcels")
    check(all(len(p) == 9 for p in subdivision),
          "each nine characters wide with a leading zero")
    check(all(len(s) == 8 for s in stripped),
          "and eight wide after a spreadsheet read them as numbers")
    r = reconcile(subdivision, stripped, fl)
    check(r.matched == 312,
          "all 312 reconcile once the lost zero is padded back  "
          "<-- pinned defect")
    check(r.verdict == RECONCILES, "so the whole subdivision reconciles")
    r = reconcile(subdivision, stripped, fl.replace(pad_to=None))
    check(r.matched == 0,
          "and with padding off NOT ONE of them matches, which is the join "
          "that succeeded  <-- pinned defect")
    check(len(r.gis_only) == 312 and len(r.roll_only) == 312,
          "every parcel is reported on one side only")
    check(r.verdict == DOES_NOT, "which is the answer nobody had for 9 months")
    check(reconcile(subdivision, stripped, generic).matched == 0,
          "generic does not repair it either: padding is a rule you ask for")
    r = reconcile(subdivision, [str(int(p)) for p in subdivision[:311]], fl)
    check(r.matched == 311 and len(r.gis_only) == 1,
          "one lot missing from the roll is one parcel reported")

    # ---- empty sides
    r = reconcile([], [], fl)
    check(r.verdict == RECONCILES,
          "two empty sides reconcile: there is nothing that failed to match")
    check(r.matched == 0 and r.width == 0,
          "with nothing matched and no width to pad to")
    check(describe(r)[-1] == "VERDICT: RECONCILES", "and the report says so")
    r = reconcile(["12345"], [], fl)
    check(r.verdict == DOES_NOT and len(r.gis_only) == 1,
          "an empty roll leaves every parcel unmatched")
    check(r.roll_only == [], "and nothing on the other side")
    check(r.width == 5, "the width comes from the side that has records")
    r = reconcile([], ["12345"], fl)
    check(r.verdict == DOES_NOT and len(r.roll_only) == 1,
          "an empty parcel layer leaves every roll record unmatched")
    check(r.gis_only == [], "and nothing on the other side")
    r = reconcile(["", "   ", None], [], fl)
    check(r.matched == 0 and len(r.rejected) == 3,
          "a side of blanks makes no keys at all")
    check(r.width == 0, "and sets no padding width")
    check(r.verdict == DOES_NOT, "blank identifiers do not reconcile")

    # ---- a rejected identifier cannot change anybody else's key
    r = reconcile(["00123001000", "1234567890123456789"], ["123001000"], fl)
    check(r.width == 11,
          "a rejected 19 digit identifier does not set the padding width for "
          "the rest of the file  <-- pinned defect")
    check(r.matched == 1, "so the other parcel still reconciles")
    check(len(r.rejected) == 1 and r.rejected[0].reason == TOO_LONG,
          "and the rejected one is reported, not dropped  <-- pinned defect")
    check(r.verdict == DOES_NOT,
          "a rejected identifier means the file does not reconcile")
    check([e.shown for e in r.gis_only] == [],
          "a rejected identifier is not ALSO reported as unmatched: it is one "
          "finding, not two  <-- pinned defect")

    # ---- validation
    raises(lambda: prepare("12345", fl),
           "a string where a list of identifiers belongs raises")
    raises(lambda: prepare(["12345"], None), "preparing with no rule raises")
    raises(lambda: reconcile([], [], None), "reconciling with no rule raises")
    raises(lambda: reconcile("a", [], fl), "a non-list gis side raises")
    raises(lambda: reconcile([], "a", fl), "a non-list roll side raises")
    raises(lambda: describe(reconcile([], [], fl), sample=-1),
           "a negative sample raises")
    raises(lambda: as_json(reconcile([], [], fl), sample=-1),
           "a negative sample raises in json too")

    # ---- rendering
    r = reconcile(gis, roll, fl)
    lines = describe(r)
    check(lines[0].startswith("KEY RULE  profile florida-nal"),
          "the report opens with the rule it used")
    check("pad numbers to 11" in lines[0],
          "naming the width it padded to, because that width was inferred "
          "from the data  <-- pinned defect")
    check("ceiling 18 characters" in lines[0] and "reject non-ASCII" in lines[0],
          "and the ceiling and the ASCII rule")
    check("fold case" in lines[0] and "strip punctuation" in lines[0],
          "and what it did to the text")
    check(any(l.startswith("MATCHED   3 key(s)") for l in lines),
          "the match count is a line")
    check(any("GIS ONLY  1 parcel(s) with no roll record" in l
              for l in lines), "class 1 is counted")
    check(any("ROLL ONLY 1 roll record(s) with no parcel" in l
              for l in lines), "class 2 is counted")
    check(any("00999-001-000  ->  00999001000" in l for l in lines),
          "and each one is printed as it arrived and as it was looked up")
    check(lines[-1] == "VERDICT: DOES NOT RECONCILE", "the verdict is last")
    check("no padding" in describe(reconcile(gis, roll,
                                             fl.replace(pad_to=None)))[0],
          "padding off says so in the rule line")
    check("keep case" in describe(reconcile([], [],
                                            fl.replace(fold_case=False)))[0],
          "and so does keeping case")
    check("keep punctuation" in describe(reconcile([], [], generic))[0],
          "and keeping punctuation")
    check("allow non-ASCII" in describe(reconcile([], [], generic))[0],
          "and allowing non-ASCII")
    check("drop the last character"
          in describe(reconcile([], [],
                                fl.replace(strip_check_digit=True)))[0],
          "and dropping a check digit")
    check("nothing to pad" in describe(reconcile([], [], fl))[0],
          "an auto width with no records says there was nothing to pad, "
          "rather than claiming a width of zero")
    check("ceiling" not in describe(reconcile([], [],
                                              fl.replace(max_len=0)))[0],
          "a ceiling of zero is not printed as a ceiling")

    many = ["1%03d" % i for i in range(30)]
    lines = describe(reconcile(many, [], fl), sample=3)
    check(len([l for l in lines if "  ->  " in l]) == 3,
          "the sample limits how many records are listed")
    check(any("... 27 more" in l for l in lines), "and the rest are counted")
    check(any("GIS ONLY  30 parcel(s)" in l for l in lines),
          "while the count itself is complete")
    check(len([l for l in describe(reconcile(many, [], fl), sample=0)
               if "  ->  " in l]) == 0, "a sample of zero lists none")
    default_lines = describe(reconcile(many, [], fl))
    check(len([l for l in default_lines if "  ->  " in l]) == 10,
          "and the default sample lists ten of them, which is what "
          "DEFAULT_SAMPLE is for  <-- pinned defect")
    check(any("... 20 more" in l for l in default_lines),
          "counting the twenty it did not list")
    r_many = reconcile(["%d" % i for i in range(40)],
                       ["%d" % (i + 1000) for i in range(40)], fl)
    check(len(describe(r_many, sample=2)) == 13,
          "eighty unmatched records sampled at two is a thirteen line report")
    check(len(describe(r_many, sample=40)) == 87,
          "and the same result listed in full is eighty-seven, so the sample "
          "really is what shortens it  <-- pinned defect")
    collide = ["0%d" % i for i in range(1, 12)] + ["%d" % i
                                                   for i in range(1, 12)]
    r = reconcile(collide, [], fl)
    check(len(r.collisions) == 11, "eleven contested keys")
    check(any("... 1 more" in l for l in describe(r, sample=10)),
          "and the collision list is sampled as well")

    # ---- the json rendering
    r = reconcile(gis, roll, fl)
    doc = as_json(r)
    check(doc["verdict"] == DOES_NOT, "the json carries the verdict")
    check(doc["profile"] == "florida-nal", "and the profile")
    check(doc["pad_width"] == 11, "and the width it padded to")
    check(doc["matched"] == 3, "and the match count")
    check(doc["gis_records"] == 4 and doc["roll_records"] == 4,
          "and how many records it read on each side")
    check(doc["gis_only"][0]["identifier"] == "00999-001-000",
          "an unmatched parcel is named")
    check(doc["gis_only"][0]["key"] == "00999001000", "with its key")
    check(doc["roll_only"][0]["identifier"] == "00888001000",
          "and so is an unmatched roll record")
    check(doc["counts"]["gis_only"] == 1 and doc["counts"]["roll_only"] == 1,
          "the counts are complete even when the lists are sampled")
    doc = as_json(reconcile(many, [], fl), sample=3)
    check(len(doc["gis_only"]) == 3 and doc["counts"]["gis_only"] == 30,
          "a sampled json says how many it did not list  <-- pinned defect")
    doc = as_json(reconcile(many, [], fl))
    check(len(doc["gis_only"]) == 10 and doc["counts"]["gis_only"] == 30,
          "and the json's own default lists ten, the same as the report  "
          "<-- pinned defect")
    doc = as_json(reconcile(["12345"], ["1234567890123456789"], fl))
    check(doc["rejected"][0]["reason"] == TOO_LONG,
          "a rejected identifier reaches the json with its reason")
    check("scheme" in doc["rejected"][0]["detail"],
          "and the sentence that explains it")
    doc = as_json(reconcile(["12345", "12345"], [], fl))
    check(doc["duplicates"][0]["count"] == 2,
          "a duplicate reaches the json with its count")
    check(json.loads(json.dumps(as_json(reconcile(gis, roll, fl))))
          == as_json(reconcile(gis, roll, fl)),
          "the whole document survives a round trip through json")

    # ---- the exception rows
    rows = exceptions(reconcile(gis, roll, fl))
    check(len(rows) == 2, "two exception rows for two unmatched records")
    check(rows[0][:2] == ("gis", "no-roll-record"),
          "each carries its side and its class")
    check(rows[0][2] == "00999-001-000" and rows[0][3] == "00999001000",
          "and the identifier and the key")
    check(rows[1][:2] == ("roll", "no-parcel"), "the roll side too")
    rows = exceptions(reconcile(["12345", "12345"], ["12345"], fl))
    check([r[1] for r in rows] == ["duplicate", "duplicate"],
          "a duplicate is written once per record, so the row count is the "
          "record count")
    rows = exceptions(reconcile(["0123456", "123456"], [], fl))
    check([r[1] for r in rows] == ["collision", "collision"],
          "a collision writes both originals")
    check(all(r[3] == "0123456" for r in rows), "under the key they share")
    rows = exceptions(reconcile(["", "1234567890123456789"], [], fl))
    check([r[1] for r in rows] == ["rejected", "rejected"],
          "a rejected identifier is an exception row too")
    check(rows[0][2] == "" and rows[0][3] == "",
          "an empty identifier is written as empty, with no key")
    check(exceptions(reconcile(["1"], ["1"], fl)) == [],
          "a file that reconciles has no exception rows")

    # ---- the harness itself. A check() that cannot record a failure would
    # report every defect above as a pass, which is the one failure no other
    # assertion here could see.
    quiet = sys.stdout
    sys.stdout = io.StringIO()
    mark = len(failed)
    try:
        check(False, "probe: a false condition must be recorded as a failure")
        raises(lambda: None, "probe: a call that raises nothing must fail")
        raises(lambda: [][0], "probe: the wrong exception must fail")
    finally:
        sys.stdout = quiet
    probe = failed[mark:]
    del failed[mark:]
    check(len(probe) == 3,
          "check() and raises() really do record a failure  <-- pinned defect")
    check("no error raised" in probe[1] and "wrong exception" in probe[2],
          "and say which way the call under test went wrong")

    # ---- the io layer, against real files in a temporary directory.
    def capture(fn):
        """(what fn returned, everything it printed to either stream)."""
        buf = io.StringIO()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = buf
        try:
            result = fn()
        finally:
            sys.stdout, sys.stderr = real_out, real_err
        return result, buf.getvalue()

    def write(path, data):
        with open(path, "wb") as fh:
            fh.write(data)

    tmp = tempfile.mkdtemp(prefix="nalmatch-selftest-")
    try:
        # A parcel layer and a roll extract that tell the whole story: three
        # parcels that reconcile once the zeros are padded back, one parcel
        # the roll has never heard of, one roll record with no parcel, a
        # blank, and an identifier from another county's scheme.
        parcels_csv = os.path.join(tmp, "parcels.csv")
        write(parcels_csv,
              b"OBJECTID,PARCEL_ID,SUBDIV\n"
              b"1,00123-001-000,PINE RIDGE\n"
              b"2,00123-001-001,PINE RIDGE\n"
              b"3,00123-001-002,PINE RIDGE\n"
              b"4,00999-001-000,ORPHAN\n"
              b"5,,NO ID\n"
              b"6,1234567890123456789,FOREIGN\n")
        roll_csv = os.path.join(tmp, "nal.csv")
        write(roll_csv,
              b"CO_NO,PARCEL_ID,JV\n"
              b"42,123001000,150000\n"
              b"42,123001001,151000\n"
              b"42,123001002,152000\n"
              b"42,888001000,99000\n")

        fields, rows = read_csv_rows(parcels_csv)
        check(fields == ["OBJECTID", "PARCEL_ID", "SUBDIV"],
              "a CSV's header row becomes the field list, in file order")
        check(len(rows) == 6, "and every data row is read")
        check(column(rows, "PARCEL_ID")[0] == "00123-001-000",
              "a column comes back in row order")
        check(column(rows, "PARCEL_ID")[4] == "",
              "an empty cell comes back as an empty string")
        check(column(rows, "NO_SUCH_FIELD") == [None] * 6,
              "asking for a field that is not there gives blanks, not a "
              "KeyError")
        check(all(isinstance(v, str) for v in column(rows, "PARCEL_ID")),
              "csv gives text for every cell, which is why an int identifier "
              "is refused rather than handled  <-- pinned defect")

        bom = os.path.join(tmp, "bom.csv")
        write(bom, b"\xef\xbb\xbfPARCEL_ID,JV\n123001000,1\n")
        check(read_csv_rows(bom)[0][0] == "PARCEL_ID",
              "a byte order mark does not become part of the first field "
              "name  <-- pinned defect")
        latin = os.path.join(tmp, "latin.csv")
        write(latin, b"PARCEL_ID\n123\xe9\n")
        check(len(read_csv_rows(latin)[1]) == 1,
              "a byte that is not UTF-8 is replaced, not fatal")
        # A row with fewer cells than the header is how a real None reaches
        # the core: csv fills the missing trailing fields with None.
        ragged = os.path.join(tmp, "ragged.csv")
        write(ragged, b"JV,PARCEL_ID\n150000,123001000\n151000\n")
        check(column(read_csv_rows(ragged)[1], "PARCEL_ID")
              == ["123001000", None],
              "a short row gives None for the identifier, not an empty string")
        rc, out = capture(lambda: main([ragged, roll_csv]))
        check(rc == 1 and "REJECTED  1 identifier(s)" in out,
              "and that missing cell is rejected rather than crashing the run")
        check("None" not in out,
              "with the word None printed nowhere  <-- pinned defect")
        write(os.path.join(tmp, "empty.csv"), b"")
        raises(lambda: read_csv_rows(os.path.join(tmp, "empty.csv")),
               "a CSV with no header row raises rather than reporting nothing")
        headers_only = os.path.join(tmp, "headers.csv")
        write(headers_only, b"PARCEL_ID,JV\n")
        check(read_csv_rows(headers_only)[1] == [],
              "a CSV of headers and nothing else reads as no rows")
        missing = None
        try:
            read_csv_rows(os.path.join(tmp, "no-such.csv"))
        except OSError as exc:
            missing = exc
        check(isinstance(missing, OSError),
              "a CSV that does not exist raises the OSError main turns into "
              "exit 2")

        # ---- main(), end to end
        rc, out = capture(lambda: main([parcels_csv, roll_csv]))
        check(rc == 1, "a pair of files that does not reconcile exits 1")
        check("VERDICT: DOES NOT RECONCILE" in out, "and says so")
        check("MATCHED   3 key(s)" in out,
              "three parcels reconcile through the padding rule, read off "
              "disk  <-- pinned defect")
        check("GIS ONLY  1 parcel(s)" in out, "one parcel has no roll record")
        check("00999-001-000  ->  00999001000" in out, "named with its key")
        check("ROLL ONLY 1 roll record(s)" in out,
              "one roll record has no parcel")
        check("REJECTED  2 identifier(s)" in out,
              "the blank and the foreign identifier are both rejected")
        check("belongs to a different identifier scheme" in out,
              "and the 19 digit one says why  <-- pinned defect")
        check("pad numbers to 11" in out,
              "the padding width is reported, and it came from the data")
        check("nal.csv" in out and "parcels.csv" in out,
              "the header names both files")

        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--pad", "off"]))
        check(rc == 1, "--pad off still exits 1")
        check("MATCHED   0 key(s)" in out,
              "and NOTHING matches, which is the join in the story  "
              "<-- pinned defect")
        check("GIS ONLY  4 parcel(s)" in out,
              "every readable parcel is reported as missing from the roll")
        check("no padding" in out, "the rule line says padding was off")

        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--json"]))
        check(rc == 1, "--json exits the same way")
        doc = json.loads(out)
        check(doc["matched"] == 3,
              "and stdout is json and nothing else, so a script can pipe it")
        check(doc["counts"]["rejected"] == 2, "carrying the same counts")
        check(doc["pad_width"] == 11, "and the inferred width")

        # A file whose identifier column is named something else, which is
        # every GIS layer.
        other = os.path.join(tmp, "other.csv")
        write(other, b"PARCELNO,ACRES\n00123-001-000,1.1\n"
                     b"00123-001-001,1.2\n00123-001-002,1.3\n")
        rc, out = capture(lambda: main([other, roll_csv,
                                        "--gis-id-field", "PARCELNO"]))
        check(rc == 1 and "MATCHED   3 key(s)" in out,
              "--gis-id-field reads a differently named column")
        check("ROLL ONLY 1" in out, "and the roll side is unchanged")
        rc, out = capture(lambda: main([other, roll_csv]))
        check(rc == 64,
              "without it the default column is missing and that is a usage "
              "error, not an empty report  <-- pinned defect")
        check("PARCELNO" in out and "ACRES" in out,
              "and the error lists the fields the file does have")
        check(DEFAULT_ID_FIELD in out,
              "naming the column it looked for")
        rc, out = capture(lambda: main([parcels_csv, other,
                                        "--roll-id-field", "NOPE"]))
        check(rc == 64, "the same for --roll-id-field")
        rc, out = capture(lambda: main([other, other,
                                        "--gis-id-field", "PARCELNO",
                                        "--roll-id-field", "PARCELNO"]))
        check(rc == 0,
              "and --roll-id-field reads a differently named roll column too")
        check("VERDICT: RECONCILES" in out,
              "those three parcels reconcile against themselves, so a clean "
              "run really does exit 0  <-- pinned defect")
        check("MATCHED   3 key(s)" in out, "with all three matched")

        # The refusal, end to end.
        merge_csv = os.path.join(tmp, "merge.csv")
        write(merge_csv, b"PARCEL_ID\n0123456\n123456\n")
        rc, out = capture(lambda: main([merge_csv, roll_csv]))
        check(rc == 3, "a run whose rule merges two parcels exits 3")
        check("VERDICT: REFUSED" in out, "and says REFUSED")
        check("0123456" in out and "123456" in out, "naming both originals")
        check("MATCHED" not in out,
              "and reporting no counts at all  <-- pinned defect")
        rc, out = capture(lambda: main([merge_csv, roll_csv, "--pad", "off"]))
        check(rc == 1,
              "with padding off the same file is reported rather than refused")
        check("GIS ONLY  2 parcel(s)" in out, "as two unmatched parcels")

        # ---- writing the exceptions. Nothing is written without --apply.
        out_csv = os.path.join(tmp, "exceptions.csv")
        rc, out = capture(lambda: main([parcels_csv, roll_csv,
                                        "--write-csv", out_csv]))
        check(rc == 1, "a dry run exits on the finding, not on the write")
        check(not os.path.exists(out_csv),
              "--write-csv alone writes NOTHING  <-- pinned defect")
        check("nothing was written" in out, "and says so")
        check("4 exception row(s)" in out, "naming what it would have written")

        rc, out = capture(lambda: main([parcels_csv, roll_csv,
                                        "--write-csv", out_csv, "--apply"]))
        check(rc == 1, "the exit code still reports the finding")
        check(os.path.exists(out_csv), "--apply writes the file")
        check("wrote 4 exception row(s)" in out,
              "and says how many rows went into it, which is the only count "
              "the operator sees about the write  <-- pinned defect")
        with open(out_csv, "r", newline="", encoding="utf-8") as fh:
            written = list(csv.reader(fh))
        check(written[0] == ["SIDE", "CLASS", "IDENTIFIER", "KEY", "DETAIL"],
              "with a header row")
        check(len(written) == 5, "and one row per exception")
        classes = sorted(set(row[1] for row in written[1:]))
        check(classes == ["no-parcel", "no-roll-record", "rejected"],
              "covering every class this run found")
        check(["gis", "no-roll-record", "00999-001-000", "00999001000"]
              == written[1][:4],
              "each row carries the side, the class, the identifier and the "
              "key")
        check(any(row[2] == "1234567890123456789" for row in written),
              "the foreign identifier is in the file, written whole  "
              "<-- pinned defect")
        rejected_rows = [row for row in written[1:] if row[1] == "rejected"]
        check(len(rejected_rows) == 2,
              "both rejected identifiers reach the file, so the check below "
              "is not passing over an empty list  <-- pinned defect")
        check(not any(row[3] for row in rejected_rows),
              "a rejected identifier is written with no key, because it never "
              "made one")

        # Overwriting is proved by putting something else in the file first.
        # Checking only that the file still exists would pass if the second
        # run had skipped the write altogether.
        write(out_csv, b"STALE,ROWS,FROM,LAST,WEEK\n9,9,9,9,9\n")
        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--write-csv",
                                        out_csv, "--apply"]))
        with open(out_csv, "r", newline="", encoding="utf-8") as fh:
            again = list(csv.reader(fh))
        check(rc == 1 and again == written,
              "--apply over an existing file replaces it: the authorisation "
              "is the flag  <-- pinned defect")
        check(not any("STALE" in cell for row in again for cell in row),
              "and not one stale row survives the rewrite  <-- pinned defect")
        rc, out = capture(lambda: main([merge_csv, roll_csv, "--write-csv",
                                        os.path.join(tmp, "never.csv"),
                                        "--apply"]))
        check(rc == 3, "a refused run still exits 3 with --apply")
        check(not os.path.exists(os.path.join(tmp, "never.csv")),
              "and writes NOTHING, because the rule that made those rows "
              "merges parcels  <-- pinned defect")
        nowhere = os.path.join(tmp, "no-such-dir", "exceptions.csv")
        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--write-csv",
                                        nowhere, "--apply"]))
        check(rc == 2,
              "a write into a directory that does not exist exits 2 rather "
              "than ending in a traceback  <-- pinned defect")
        check("could not write" in out, "and says which step failed")
        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--apply"]))
        check(rc == 64,
              "--apply with nothing to write is a usage error, so it can "
              "never look like it did something")

        # A clean pair writes an empty exception file rather than none.
        clean_out = os.path.join(tmp, "clean.csv")
        rc, out = capture(lambda: main([other, other, "--roll-id-field",
                                        "PARCELNO", "--gis-id-field",
                                        "PARCELNO", "--write-csv", clean_out,
                                        "--apply"]))
        check(rc == 0, "a file reconciled against itself exits 0")
        with open(clean_out, "r", newline="", encoding="utf-8") as fh:
            check(len(list(csv.reader(fh))) == 1,
                  "and the exception file holds its header and nothing else")

        # ---- the profiles and the rule flags, end to end
        dashes = os.path.join(tmp, "dashes.csv")
        write(dashes, b"PARCEL_ID\n12-345\n12-346\n")
        plain = os.path.join(tmp, "plain.csv")
        write(plain, b"PARCEL_ID\n12345\n12346\n")
        rc, out = capture(lambda: main([dashes, plain]))
        check(rc == 0 and "VERDICT: RECONCILES" in out,
              "florida-nal reconciles a dashed layer against a plain roll")
        rc, out = capture(lambda: main([dashes, plain, "--profile", "generic"]))
        check(rc == 1 and "MATCHED   0" in out,
              "generic matches none of them, because it strips no punctuation")
        check("profile generic" in out, "and says which profile it used")
        rc, out = capture(lambda: main([dashes, plain, "--profile", "generic",
                                        "--punctuation", "strip"]))
        check(rc == 0,
              "--punctuation strip turns that one rule on over generic")
        rc, out = capture(lambda: main([dashes, plain, "--punctuation",
                                        "keep"]))
        check(rc == 1,
              "and --punctuation keep turns it off over florida-nal")
        rc, out = capture(lambda: main([dashes, plain, "--profile", "nope"]))
        check(rc == 64 and "unknown profile" in out,
              "an unknown profile is a usage error that names the ones there "
              "are")

        case_csv = os.path.join(tmp, "case.csv")
        write(case_csv, b"PARCEL_ID\nr12345\n")
        upper_csv = os.path.join(tmp, "upper.csv")
        write(upper_csv, b"PARCEL_ID\nR12345\n")
        rc, out = capture(lambda: main([case_csv, upper_csv]))
        check(rc == 0, "case is folded by default")
        rc, out = capture(lambda: main([case_csv, upper_csv, "--case", "keep"]))
        check(rc == 1, "and --case keep stops that")

        # One parcel on the two sides, with a check digit that was recomputed
        # differently. The rule drops the last character from BOTH sides,
        # which is the only symmetric thing it can do.
        check_csv = os.path.join(tmp, "check.csv")
        write(check_csv, b"PARCEL_ID\n1234567\n")
        recheck = os.path.join(tmp, "recheck.csv")
        write(recheck, b"PARCEL_ID\n1234568\n")
        rc, out = capture(lambda: main([check_csv, recheck]))
        check(rc == 1,
              "a trailing check digit is not stripped by default, so two "
              "spellings of one parcel do not reconcile  <-- pinned defect")
        rc, out = capture(lambda: main([check_csv, recheck, "--check-digit",
                                        "strip"]))
        check(rc == 0, "--check-digit strip reconciles them")
        check("drop the last character" in out, "and the rule line says so")
        both_csv = os.path.join(tmp, "both.csv")
        write(both_csv, b"PARCEL_ID\n1234567\n1234568\n")
        rc, out = capture(lambda: main([both_csv, recheck, "--check-digit",
                                        "strip"]))
        check(rc == 3,
              "and when BOTH spellings are in the layer, stripping the check "
              "digit merges two records and the run is refused  "
              "<-- pinned defect")
        check("1234567" in out and "1234568" in out, "naming both")
        rc, out = capture(lambda: main([both_csv, recheck]))
        check(rc == 1,
              "while the default rule keeps them apart and reports them")

        long_csv = os.path.join(tmp, "long.csv")
        write(long_csv, b"PARCEL_ID\n1234567890123456789\n")
        rc, out = capture(lambda: main([long_csv, long_csv]))
        check(rc == 1 and "REJECTED  2" in out,
              "a 19 digit identifier is rejected on both sides")
        check("1234567890123456789" in out, "and printed whole, not truncated")
        rc, out = capture(lambda: main([long_csv, long_csv, "--max-len", "19"]))
        check(rc == 0, "--max-len 19 lets it through")
        rc, out = capture(lambda: main([long_csv, long_csv, "--max-len", "0"]))
        check(rc == 0, "and --max-len 0 removes the ceiling altogether")
        rc, out = capture(lambda: main([long_csv, long_csv, "--max-len", "-1"]))
        check(rc == 64, "a negative ceiling is a usage error")

        uni = os.path.join(tmp, "unicode.csv")
        write(uni, u"PARCEL_ID\n12345\u00d1\n".encode("utf-8"))
        rc, out = capture(lambda: main([uni, uni]))
        check(rc == 1 and "REJECTED  2" in out,
              "a non-ASCII identifier is rejected by florida-nal")
        check("outside ASCII" in out, "and says why")
        rc, out = capture(lambda: main([uni, uni, "--non-ascii", "allow"]))
        check(rc == 0, "--non-ascii allow reconciles it against itself")
        check("MATCHED   1 key(s)" in out and "allow non-ASCII" in out,
              "matching it verbatim, which the rule line says it did")
        rc, out = capture(lambda: main([uni, uni, "--profile", "generic"]))
        check(rc == 0, "generic allows it without a flag")

        pad_csv = os.path.join(tmp, "pad.csv")
        write(pad_csv, b"PARCEL_ID\n42\n")
        pad2_csv = os.path.join(tmp, "pad2.csv")
        write(pad2_csv, b"PARCEL_ID\n0000000042\n")
        rc, out = capture(lambda: main([pad_csv, pad2_csv]))
        check(rc == 0 and "pad numbers to 10" in out,
              "the width is taken from the wider side")
        rc, out = capture(lambda: main([pad_csv, pad_csv, "--pad", "8"]))
        check(rc == 0 and "pad numbers to 8" in out,
              "--pad 8 sets the width by hand")
        rc, out = capture(lambda: main([pad_csv, pad_csv, "--pad", "auto"]))
        check(rc == 0 and "pad numbers to 2" in out,
              "--pad auto asks the data")
        rc, out = capture(lambda: main([pad_csv, pad_csv, "--pad", "0"]))
        check(rc == 64, "--pad 0 is a usage error, not a silent auto")
        rc, out = capture(lambda: main([pad_csv, pad_csv, "--pad", "-3"]))
        check(rc == 64, "and so is a negative width")
        rc, out = capture(lambda: main([pad_csv, pad_csv, "--pad", "wide"]))
        check(rc == 64 and "auto, off, or a width" in out,
              "and a word that is not auto or off")

        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--sample",
                                        "1"]))
        check(rc == 1 and "REJECTED  2 identifier(s)" in out,
              "--sample shortens the lists, not the counts")
        check("... 1 more" in out, "and says how many it did not list")
        rc, out = capture(lambda: main([parcels_csv, roll_csv, "--sample",
                                        "-1"]))
        check(rc == 64, "a negative sample is a usage error")

        # ---- files that cannot be read
        rc, out = capture(lambda: main([os.path.join(tmp, "no-such.csv"),
                                        roll_csv]))
        check(rc == 2, "a parcel file that does not exist exits 2")
        check("could not read" in out, "and says which step failed")
        rc, out = capture(lambda: main([parcels_csv,
                                        os.path.join(tmp, "no-such.csv")]))
        check(rc == 2, "a roll file that does not exist exits 2")
        rc, out = capture(lambda: main([parcels_csv,
                                        os.path.join(tmp, "empty.csv")]))
        check(rc == 2, "a CSV with no header row exits 2")
        rc, out = capture(lambda: main([headers_only, headers_only]))
        check(rc == 0 and "MATCHED   0 key(s)" in out,
              "two empty tables reconcile, because nothing failed to match")
        check("VERDICT: RECONCILES" in out, "and say so")

        # ---- usage
        rc, out = capture(lambda: main([]))
        check(rc == 64, "no files at all is a usage error")
        check("--self-test" in out, "and the message names the way to try it")
        rc, out = capture(lambda: main([parcels_csv]))
        check(rc == 64, "one file is a usage error too")
        rc, out = capture(lambda: main(["--self-test", "--json"]))
        check(rc == 64,
              "--self-test with another flag is a usage error, so a green run "
              "can never be a green run of something else")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        check(not os.path.isdir(tmp),
              "the self-test leaves no temporary directory behind")

    # ---- argument handling. Every flag that can change an answer is read,
    # and every flag that can write or merge defaults to OFF.
    a = _parse([])
    check(a.gis is None and a.roll is None,
          "no files parse to None rather than failing")
    check(a.apply is False, "--apply defaults to OFF")
    check(a.write_csv is None, "--write-csv defaults to writing nothing")
    check(a.self_test is False, "--self-test defaults to OFF")
    check(a.json is False, "--json defaults to OFF")
    check(a.profile == DEFAULT_PROFILE, "--profile defaults to the configured "
                                        "profile")
    check(a.gis_id_field == DEFAULT_ID_FIELD
          and a.roll_id_field == DEFAULT_ID_FIELD,
          "both id fields default to the configured column")
    check(a.sample == DEFAULT_SAMPLE, "--sample defaults to the configured size")
    check(a.case is None and a.punctuation is None and a.pad is None
          and a.check_digit is None and a.max_len is None
          and a.non_ascii is None,
          "and every rule override defaults to 'whatever the profile says'  "
          "<-- pinned defect")
    check(_parse(["a.csv", "b.csv"]).gis == "a.csv", "the parcel file is read")
    check(_parse(["a.csv", "b.csv"]).roll == "b.csv", "the roll file is read")
    check(_parse(["a.csv", "b.csv", "--apply"]).apply is True,
          "--apply is read")
    check(_parse(["a.csv", "b.csv", "--write-csv", "x.csv"]).write_csv
          == "x.csv", "--write-csv is read")
    check(_parse(["a.csv", "b.csv", "--json"]).json is True, "--json is read")
    check(_parse(["a.csv", "b.csv", "--profile", "generic"]).profile
          == "generic", "--profile is read")
    check(_parse(["a.csv", "b.csv", "--gis-id-field", "P"]).gis_id_field == "P",
          "--gis-id-field is read")
    check(_parse(["a.csv", "b.csv", "--roll-id-field", "P"]).roll_id_field
          == "P", "--roll-id-field is read")
    check(_parse(["a.csv", "b.csv", "--case", "keep"]).case == "keep",
          "--case is read")
    check(_parse(["a.csv", "b.csv", "--punctuation", "keep"]).punctuation
          == "keep", "--punctuation is read")
    check(_parse(["a.csv", "b.csv", "--pad", "off"]).pad == "off",
          "--pad is read")
    check(_parse(["a.csv", "b.csv", "--check-digit", "strip"]).check_digit
          == "strip", "--check-digit is read")
    check(_parse(["a.csv", "b.csv", "--max-len", "9"]).max_len == 9,
          "--max-len is read")
    check(_parse(["a.csv", "b.csv", "--non-ascii", "allow"]).non_ascii
          == "allow", "--non-ascii is read")
    check(_parse(["a.csv", "b.csv", "--sample", "3"]).sample == 3,
          "--sample is read")
    check(_parse(["--self-test"]).self_test is True, "--self-test is read")

    # build_rules turns those flags into exactly one rule change each.
    base = _parse(["a.csv", "b.csv"])
    check(build_rules(base).name == "florida-nal",
          "no override gives the profile unchanged")
    check(build_rules(_parse(["a", "b", "--case", "keep"])).fold_case is False,
          "--case keep switches one rule")
    check(build_rules(_parse(["a", "b", "--case", "fold"])).fold_case is True,
          "and --case fold switches it back")
    check(build_rules(_parse(["a", "b", "--punctuation",
                              "keep"])).strip_punctuation is False,
          "--punctuation keep switches one rule")
    check(build_rules(_parse(["a", "b", "--profile", "generic",
                              "--punctuation",
                              "strip"])).strip_punctuation is True,
          "and strip switches it the other way")
    check(build_rules(_parse(["a", "b", "--pad", "off"])).pad_to is None,
          "--pad off turns padding off")
    check(build_rules(_parse(["a", "b", "--pad", "11"])).pad_to == 11,
          "--pad 11 fixes the width")
    check(build_rules(_parse(["a", "b", "--profile", "generic", "--pad",
                              "auto"])).pad_to == 0,
          "--pad auto turns it on over generic")
    check(build_rules(_parse(["a", "b", "--check-digit",
                              "strip"])).strip_check_digit is True,
          "--check-digit strip turns it on")
    check(build_rules(_parse(["a", "b", "--check-digit",
                              "keep"])).strip_check_digit is False,
          "and keep turns it off")
    check(build_rules(_parse(["a", "b", "--max-len", "9"])).max_len == 9,
          "--max-len sets the ceiling")
    check(build_rules(_parse(["a", "b", "--non-ascii",
                              "allow"])).ascii_only is False,
          "--non-ascii allow turns the ASCII rule off")
    check(build_rules(_parse(["a", "b", "--non-ascii",
                              "reject"])).ascii_only is True,
          "and reject turns it on")
    check(build_rules(_parse(["a", "b", "--profile", "generic"])).name
          == "generic", "--profile picks the other profile")
    raises(lambda: build_rules(_parse(["a", "b", "--profile", "nope"])),
           "an unknown profile raises")
    raises(lambda: build_rules(_parse(["a", "b", "--pad", "nope"])),
           "a --pad that is neither auto, off nor a number raises")
    raises(lambda: build_rules(_parse(["a", "b", "--pad", "0"])),
           "a --pad width of zero raises rather than meaning auto")
    raises(lambda: build_rules(_parse(["a", "b", "--max-len", "-2"])),
           "a negative ceiling raises")

    # ---- nothing here opens a socket, and the source says so
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as fh:
        source = fh.read()
    check(re.search(r"^\s*import\s+(urllib|socket|http|ftplib|requests)",
                    source, re.M) is None,
          "nalmatch imports no network module: there is no upload path to "
          "audit, and no credential for one to carry")
    check(re.search(r"^\s*(def|class)\s", source, re.M) is not None,
          "and that search really was run over this file's own source")

    # ---- the write flag is reached only by its full spelling
    # argparse would take --ap as --apply. A prefix that lands on the write
    # flag must be refused, and the parser exits 2 without writing.
    stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        _parse(["a", "b", "--ap"])
        refused = False
    except SystemExit as exc:
        refused = exc.code == 2
    finally:
        sys.stderr = stderr
    check(refused,
          "a unique prefix of --apply is refused by the parser, not read as "
          "the write flag  <-- pinned defect")

    print("-" * 68)
    total = passed[0] + len(failed)
    if failed:
        print("%d assertions, %d failed" % (total, len(failed)))
        for f in failed:
            print("  FAILED: %s" % f)
        return 1
    print("%d assertions, 0 failed" % total)
    return 0


# ----------------------------------------------------------------------- cli

def _parse(argv):
    ap = argparse.ArgumentParser(
        prog="nalmatch.py",
        description="Reconcile a GIS parcel layer against the tax roll and "
                    "name every parcel that exists on one side only.",
        epilog="Nothing is written without --apply. A rule that would give "
               "two distinct parcels the same key is refused, not reported.",
        allow_abbrev=False,
    )
    ap.add_argument("gis", nargs="?", help="the parcel layer as a CSV")
    ap.add_argument("roll", nargs="?", help="the tax roll extract as a CSV")
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help="identifier rule to start from: florida-nal or "
                         "generic (default %s)" % DEFAULT_PROFILE)
    ap.add_argument("--gis-id-field", dest="gis_id_field",
                    default=DEFAULT_ID_FIELD,
                    help="identifier column in the parcel layer (default %s)"
                         % DEFAULT_ID_FIELD)
    ap.add_argument("--roll-id-field", dest="roll_id_field",
                    default=DEFAULT_ID_FIELD,
                    help="identifier column in the roll extract (default %s)"
                         % DEFAULT_ID_FIELD)
    ap.add_argument("--case", choices=["fold", "keep"],
                    help="fold identifiers to upper case, or leave the case "
                         "alone")
    ap.add_argument("--punctuation", choices=["strip", "keep"],
                    help="remove the separators %r, or leave them in"
                         % PUNCTUATION)
    ap.add_argument("--pad", metavar="auto|off|N",
                    help="pad all-digit identifiers with leading zeros to the "
                         "widest one seen (auto), to N characters, or not at "
                         "all (off)")
    ap.add_argument("--check-digit", dest="check_digit",
                    choices=["strip", "keep"],
                    help="drop the last character of every identifier, or "
                         "keep it")
    ap.add_argument("--max-len", dest="max_len", type=int, metavar="N",
                    help="refuse an identifier longer than N characters as "
                         "out of profile. 0 means no ceiling.")
    ap.add_argument("--non-ascii", dest="non_ascii",
                    choices=["reject", "allow"],
                    help="refuse an identifier holding a character outside "
                         "ASCII, or match it verbatim")
    ap.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                    help="how many records to list under each class "
                         "(default %d, 0 lists none)" % DEFAULT_SAMPLE)
    ap.add_argument("--write-csv", dest="write_csv", metavar="PATH",
                    help="write the exception rows to this CSV. Needs --apply.")
    ap.add_argument("--apply", action="store_true",
                    help="actually write --write-csv. Without it nothing is "
                         "written.")
    ap.add_argument("--json", action="store_true",
                    help="write the report as json on stdout instead of text")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run the assertions and exit")
    return ap.parse_args(argv)


def _ids(path, field, args_label):
    """(the identifier column, the fields the file has). Raises on a bad field."""
    fields, rows = read_csv_rows(path)
    if field not in fields:
        raise LookupError("%s has no field %r. Name the right one with %s. "
                          "It has: %s"
                          % (path, field, args_label, ", ".join(fields)))
    return column(rows, field), fields


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = _parse(argv)

    if args.self_test:
        # A self-test run that also carried --profile or --pad would report a
        # pass for a configuration nobody asked about.
        if len(argv) != 1:
            print("error: --self-test takes no other flags.", file=sys.stderr)
            return 64
        return self_test()

    if not args.gis or not args.roll:
        print("error: give a parcel CSV and a roll CSV. Use --self-test to "
              "verify the tool without either.", file=sys.stderr)
        return 64
    if args.sample < 0:
        print("error: --sample cannot be negative.", file=sys.stderr)
        return 64
    if args.apply and not args.write_csv:
        print("error: --apply authorises --write-csv, and there is no "
              "--write-csv to authorise.", file=sys.stderr)
        return 64

    try:
        rules = build_rules(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 64

    try:
        gis_ids, _ = _ids(args.gis, args.gis_id_field, "--gis-id-field")
        roll_ids, _ = _ids(args.roll, args.roll_id_field, "--roll-id-field")
    except (OSError, IOError, ValueError) as exc:
        print("error: could not read: %s" % exc, file=sys.stderr)
        return 2
    except LookupError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 64

    result = reconcile(gis_ids, roll_ids, rules)

    if args.json:
        print(json.dumps(as_json(result, args.sample), indent=2,
                         sort_keys=True))
    else:
        print("nalmatch: %s %d record(s), %s %d record(s)"
              % (args.gis, len(result.gis), args.roll, len(result.roll)))
        print("")
        for line in describe(result, args.sample):
            print(line)

    if result.refused:
        # The exception rows were computed under a rule this tool has already
        # refused. Writing them would put a merged answer in a file somebody
        # loads later, which is the failure this whole tool exists to stop.
        return 3

    if args.write_csv:
        rows = len(exceptions(result))
        if not args.apply:
            print("would write %d exception row(s) to %s, and nothing was "
                  "written. Add --apply." % (rows, args.write_csv))
        else:
            try:
                written = write_exceptions(args.write_csv, result)
            except (OSError, IOError) as exc:
                print("error: could not write %s: %s"
                      % (args.write_csv, exc), file=sys.stderr)
                return 2
            print("wrote %d exception row(s) to %s"
                  % (written, args.write_csv))

    return 0 if result.verdict == RECONCILES else 1


if __name__ == "__main__":
    sys.exit(main())
