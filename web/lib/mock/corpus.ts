/**
 * Fixture corpus.
 *
 * SYNTHETIC SAMPLE DATA, written for this repo — it is not real Enron mail. It
 * exists so the frontend is fully interactive before the Phase 2 search API is
 * built, and so the design can be judged against realistic text shapes (long
 * subjects, quoted replies, cc lists, threads). Real names from the public
 * corpus are used as addresses only, the way the shipped product will show them.
 *
 * `concepts` drives the mock semantic leg — see engine.ts.
 */

export interface MockDoc {
  id: string;
  message_id: string;
  thread_id: string;
  subject: string;
  from: string;
  from_name: string;
  to: string[];
  cc: string[];
  date: string;
  folder: string;
  mailboxes: string[];
  attachment_names: string[];
  duplicate_count: number;
  body: string;
  quoted_text: string;
  /** Latent topics, used to fake vector retrieval. */
  concepts: string[];
}

export const PEOPLE: Record<string, string> = {
  "kenneth.lay@enron.com": "Kenneth Lay",
  "jeff.skilling@enron.com": "Jeffrey Skilling",
  "andrew.fastow@enron.com": "Andrew Fastow",
  "sherron.watkins@enron.com": "Sherron Watkins",
  "richard.causey@enron.com": "Richard Causey",
  "ben.glisan@enron.com": "Ben Glisan",
  "vince.kaminski@enron.com": "Vince Kaminski",
  "louise.kitchen@enron.com": "Louise Kitchen",
  "john.arnold@enron.com": "John Arnold",
  "sara.shackleton@enron.com": "Sara Shackleton",
  "tana.jones@enron.com": "Tana Jones",
  "mark.taylor@enron.com": "Mark Taylor",
  "greg.whalley@enron.com": "Greg Whalley",
  "rebecca.mark@enron.com": "Rebecca Mark",
};

interface Seed {
  s: string;
  f: string;
  t: string[];
  c?: string[];
  d: string;
  folder: string;
  thread: string;
  att?: string[];
  dup?: number;
  body: string;
  quoted?: string;
  concepts: string[];
}

const SEEDS: Seed[] = [
  {
    s: "Raptor I structure — funding timeline",
    f: "andrew.fastow@enron.com",
    t: ["jeff.skilling@enron.com"],
    c: ["ben.glisan@enron.com", "richard.causey@enron.com"],
    d: "2000-04-18T14:22:00Z",
    folder: "sent_items",
    thread: "th-raptor-1",
    att: ["raptor_i_term_sheet.pdf"],
    concepts: ["spe", "structured-finance", "raptor", "hedging"],
    body:
      "Jeff — the Raptor I vehicle is capitalised and ready to take the first tranche. LJM2 funds the equity, Enron contributes restricted stock against the notes. The hedge sits against our merchant portfolio, so the mark-to-market swings stop showing up in the quarterly numbers.\n\nWe need Rick's sign-off on the accounting treatment before the 30th. Ben has the term sheet.",
  },
  {
    s: "RE: Raptor I structure — funding timeline",
    f: "jeff.skilling@enron.com",
    t: ["andrew.fastow@enron.com"],
    c: ["richard.causey@enron.com"],
    d: "2000-04-18T18:05:00Z",
    folder: "sent_items",
    thread: "th-raptor-1",
    concepts: ["spe", "raptor", "approval", "hedging"],
    body:
      "Approved in principle. Make sure Rick is comfortable that this is a genuine third-party hedge and that we can support the valuation if anyone asks. I do not want to be explaining the equity contribution to Arthur Andersen in October.",
    quoted:
      "> Jeff — the Raptor I vehicle is capitalised and ready to take the first\n> tranche. LJM2 funds the equity, Enron contributes restricted stock.",
  },
  {
    s: "Raptor III — credit capacity is gone",
    f: "ben.glisan@enron.com",
    t: ["andrew.fastow@enron.com", "richard.causey@enron.com"],
    d: "2001-03-12T09:41:00Z",
    folder: "raptor",
    thread: "th-raptor-3",
    att: ["raptor_iii_credit_summary.xls"],
    dup: 4,
    concepts: ["raptor", "credit", "impairment", "spe", "writedown"],
    body:
      "The credit capacity in Raptor III is effectively exhausted. The vehicle is underwater against the hedged positions and the only thing propping up the counterparty is Enron stock, which is down 28% since December.\n\nIf we mark these positions honestly this quarter we are looking at a charge somewhere north of $500 million. I do not see a way to avoid disclosing that.",
  },
  {
    s: "RE: Raptor III — credit capacity is gone",
    f: "richard.causey@enron.com",
    t: ["ben.glisan@enron.com"],
    c: ["andrew.fastow@enron.com"],
    d: "2001-03-12T16:20:00Z",
    folder: "raptor",
    thread: "th-raptor-3",
    concepts: ["raptor", "restructure", "accounting", "concealment"],
    body:
      "Before we put a number in front of anyone, let us look at cross-collateralising the four vehicles. If Raptor I and II carry excess capacity we can move it across and the aggregate position does not require a charge this period.\n\nDo not circulate the summary outside this group until we have settled the approach.",
    quoted: "> The credit capacity in Raptor III is effectively exhausted.",
  },
  {
    s: "Cross-collateralisation of the four vehicles",
    f: "andrew.fastow@enron.com",
    t: ["richard.causey@enron.com", "ben.glisan@enron.com"],
    d: "2001-03-14T11:02:00Z",
    folder: "raptor",
    thread: "th-raptor-3",
    concepts: ["raptor", "restructure", "concealment", "accounting"],
    body:
      "Agreed on cross-collateralisation. Legal thinks the documentation supports it. Net effect is that the aggregate hedge stays above water on paper and there is no quarterly charge.\n\nThis buys us two quarters. It does not fix the underlying problem, which is that the whole structure is hedged with our own equity.",
  },
  {
    s: "Accounting treatment I am not comfortable with",
    f: "sherron.watkins@enron.com",
    t: ["kenneth.lay@enron.com"],
    d: "2001-08-15T08:12:00Z",
    folder: "sent_items",
    thread: "th-watkins",
    att: ["memo_to_klay.doc"],
    dup: 9,
    concepts: ["whistleblower", "concealment", "accounting", "raptor", "risk"],
    body:
      "Has Enron become a risky place to work? For those of us who did not get rich over the last few years, can we afford to stay?\n\nI am incredibly nervous that we will implode in a wave of accounting scandals. My eight years of Enron work history will be worth nothing on my resume, the business world will consider the past successes as nothing but an elaborate accounting hoax.\n\nThe Raptor entities are not real hedges. We are hedging with our own stock. When the stock falls the hedge fails exactly when we need it.",
  },
  {
    s: "RE: Accounting treatment I am not comfortable with",
    f: "kenneth.lay@enron.com",
    t: ["sherron.watkins@enron.com"],
    d: "2001-08-22T17:44:00Z",
    folder: "sent_items",
    thread: "th-watkins",
    concepts: ["whistleblower", "review", "legal"],
    body:
      "Thank you for raising this directly with me. I have asked Vinson & Elkins to take an independent look at the issues you describe and report back. I would like to meet with you when that review is complete.",
    quoted: "> The Raptor entities are not real hedges. We are hedging with our own stock.",
  },
  {
    s: "Q3 2001 earnings — where we stand",
    f: "kenneth.lay@enron.com",
    t: ["jeff.skilling@enron.com", "greg.whalley@enron.com"],
    c: ["richard.causey@enron.com"],
    d: "2001-08-30T13:15:00Z",
    folder: "sent_items",
    thread: "th-q3",
    att: ["q3_preliminary.xls"],
    concepts: ["earnings", "writedown", "impairment", "disclosure"],
    body:
      "We need to agree the Q3 story this week. Broadband is going to take a substantial write-down and the Raptor unwind will land in the same quarter.\n\nMy preference is to take the charge once, call it non-recurring, and be very clear that the wholesale business is untouched. Drawing it out over two quarters is worse.",
  },
  {
    s: "RE: Q3 2001 earnings — where we stand",
    f: "jeff.skilling@enron.com",
    t: ["kenneth.lay@enron.com"],
    d: "2001-08-30T19:30:00Z",
    folder: "sent_items",
    thread: "th-q3",
    concepts: ["earnings", "disclosure", "writedown"],
    body:
      "Agree on a single charge. The analysts will forgive one bad quarter with a clean explanation. They will not forgive finding out in January that there was more.\n\nI want the wholesale numbers broken out separately so nobody confuses the two.",
    quoted: "> My preference is to take the charge once, call it non-recurring.",
  },
  {
    s: "Broadband impairment — preliminary numbers",
    f: "richard.causey@enron.com",
    t: ["kenneth.lay@enron.com", "jeff.skilling@enron.com"],
    d: "2001-09-04T10:05:00Z",
    folder: "sent_items",
    thread: "th-q3",
    att: ["ebs_impairment_draft.xls", "ebs_assets.pdf"],
    concepts: ["writedown", "impairment", "broadband", "earnings"],
    body:
      "Preliminary broadband impairment is $180 million, and I expect it to move up once we finish valuing the dark fibre. Combined with the Raptor unwind we are looking at roughly $1.01 billion of charges for the quarter.",
  },
  {
    s: "Mark to market on the merchant portfolio",
    f: "vince.kaminski@enron.com",
    t: ["greg.whalley@enron.com"],
    c: ["jeff.skilling@enron.com"],
    d: "2001-02-07T15:48:00Z",
    folder: "research",
    thread: "th-mtm",
    concepts: ["valuation", "risk", "modelling", "mtm"],
    body:
      "The valuation model we are using for the merchant investments assumes liquidity that does not exist for most of these positions. When research has raised this the answer has been that the structures are hedged.\n\nI have looked at the hedges. They are with related entities and the credit behind them is Enron stock. That is not a hedge, it is a circular reference.",
  },
  {
    s: "RE: Mark to market on the merchant portfolio",
    f: "greg.whalley@enron.com",
    t: ["vince.kaminski@enron.com"],
    d: "2001-02-08T09:12:00Z",
    folder: "research",
    thread: "th-mtm",
    concepts: ["valuation", "risk", "pushback"],
    body:
      "Understood, but the structures were reviewed by Andersen and by outside counsel. Put your concerns in writing to Rick Causey and I will make sure they are read.",
    quoted: "> That is not a hedge, it is a circular reference.",
  },
  {
    s: "LJM2 — conflict of interest waiver",
    f: "sara.shackleton@enron.com",
    t: ["mark.taylor@enron.com"],
    c: ["andrew.fastow@enron.com"],
    d: "2000-10-11T12:00:00Z",
    folder: "legal",
    thread: "th-ljm2",
    att: ["ljm2_waiver_draft.doc"],
    concepts: ["legal", "conflict", "ljm", "governance"],
    body:
      "Attached is the draft waiver for the board to approve, allowing Andy to serve as general partner of LJM2 while remaining CFO. The board minutes should record that the audit committee reviewed the arrangement annually.",
  },
  {
    s: "RE: LJM2 — conflict of interest waiver",
    f: "mark.taylor@enron.com",
    t: ["sara.shackleton@enron.com"],
    d: "2000-10-11T16:31:00Z",
    folder: "legal",
    thread: "th-ljm2",
    concepts: ["legal", "conflict", "ljm", "governance"],
    body:
      "The waiver language is fine. My concern is procedural: if the CFO is on both sides of a transaction, the approval trail has to be unimpeachable. Every deal needs a signed approval sheet from someone who is not Andy.",
  },
  {
    s: "Deal approval sheets — missing signatures",
    f: "tana.jones@enron.com",
    t: ["sara.shackleton@enron.com", "mark.taylor@enron.com"],
    d: "2001-05-22T11:20:00Z",
    folder: "legal",
    thread: "th-approvals",
    att: ["missing_approvals.xls"],
    concepts: ["governance", "controls", "ljm", "audit"],
    body:
      "I have gone through the LJM transaction files for 2000 and 2001. Of 34 deals, 11 have no countersigned approval sheet and 4 have approval sheets dated after the transaction closed.\n\nThis is going to be a problem in any audit.",
  },
  {
    s: "California — ancillary services bidding",
    f: "john.arnold@enron.com",
    t: ["louise.kitchen@enron.com"],
    d: "2000-12-04T08:55:00Z",
    folder: "west",
    thread: "th-ca",
    concepts: ["trading", "california", "power", "regulatory"],
    body:
      "Ancillary services prices in CAISO were dislocated again overnight. We picked up most of the spinning reserve at prices that will look indefensible in a hearing, even though every bid was inside the rules as published.\n\nSuggest we document the rule citation alongside each bid from now on.",
  },
  {
    s: "RE: California — ancillary services bidding",
    f: "louise.kitchen@enron.com",
    t: ["john.arnold@enron.com"],
    c: ["greg.whalley@enron.com"],
    d: "2000-12-04T14:10:00Z",
    folder: "west",
    thread: "th-ca",
    concepts: ["trading", "california", "regulatory", "compliance"],
    body:
      "Yes — document everything. Assume every trade in that market is read back to us by a regulator in two years. If a strategy only works because a rule is badly drafted, I want the rule reference in the file.",
  },
  {
    s: "EnronOnline volumes — November",
    f: "louise.kitchen@enron.com",
    t: ["jeff.skilling@enron.com", "greg.whalley@enron.com"],
    d: "2000-12-01T09:00:00Z",
    folder: "sent_items",
    thread: "th-eol",
    att: ["eol_november.xls"],
    concepts: ["trading", "platform", "volumes"],
    body:
      "November closed at 218,000 transactions, a record. Gas remains 61% of notional. The platform is now handling more volume in a day than the voice desk did in a week two years ago.",
  },
  {
    s: "Analyst call — questions we should expect",
    f: "greg.whalley@enron.com",
    t: ["kenneth.lay@enron.com", "jeff.skilling@enron.com"],
    d: "2001-10-12T07:30:00Z",
    folder: "sent_items",
    thread: "th-call",
    concepts: ["disclosure", "earnings", "investor", "raptor"],
    body:
      "Expect three questions and nothing else: what exactly is in the $1.2 billion equity reduction, who are the counterparties in the terminated structures, and whether the CFO had an economic interest in them.\n\nWe need one answer to the third question and everyone needs to give the same one.",
  },
  {
    s: "Equity reduction — how are we describing this",
    f: "kenneth.lay@enron.com",
    t: ["richard.causey@enron.com", "andrew.fastow@enron.com"],
    d: "2001-10-16T06:45:00Z",
    folder: "sent_items",
    thread: "th-call",
    dup: 6,
    concepts: ["disclosure", "concealment", "raptor", "earnings"],
    body:
      "The press release says the charge is non-recurring and does not mention the $1.2 billion reduction in shareholders equity. The 10-Q will have to.\n\nI would rather explain it ourselves on Tuesday than have it found in a filing on Thursday.",
  },
  {
    s: "Vinson & Elkins review — scope",
    f: "kenneth.lay@enron.com",
    t: ["sherron.watkins@enron.com"],
    c: ["mark.taylor@enron.com"],
    d: "2001-09-10T15:00:00Z",
    folder: "sent_items",
    thread: "th-watkins",
    att: ["ve_scope_letter.pdf"],
    concepts: ["legal", "review", "whistleblower"],
    body:
      "The scope of the review is the specific transactions you identified and whether the accounting treatment was supportable. It is not a re-audit and V&E will not be re-examining Andersen's work.",
  },
  {
    s: "Retention bonuses for the trading desks",
    f: "greg.whalley@enron.com",
    t: ["kenneth.lay@enron.com"],
    d: "2001-11-02T18:22:00Z",
    folder: "sent_items",
    thread: "th-retention",
    att: ["retention_schedule.xls"],
    concepts: ["retention", "people", "trading"],
    body:
      "If we lose the gas and power desks we lose the only business currently generating cash. I need authority for $50 million in retention payments this week, not after the merger closes.",
  },
  {
    s: "Dynegy merger — due diligence data room",
    f: "jeff.skilling@enron.com",
    t: ["kenneth.lay@enron.com", "greg.whalley@enron.com"],
    d: "2001-11-08T20:15:00Z",
    folder: "sent_items",
    thread: "th-dynegy",
    concepts: ["merger", "diligence", "disclosure"],
    body:
      "Dynegy's team is asking for the LJM and Raptor documentation in full. There is no version of this where we give them a partial file. Either they see it or the deal does not close.",
  },
  {
    s: "Restatement — 1997 through 2000",
    f: "richard.causey@enron.com",
    t: ["kenneth.lay@enron.com"],
    c: ["greg.whalley@enron.com"],
    d: "2001-11-08T11:40:00Z",
    folder: "sent_items",
    thread: "th-restate",
    att: ["restatement_summary.xls"],
    dup: 5,
    concepts: ["restatement", "accounting", "earnings", "concealment"],
    body:
      "The restatement reduces reported net income by $586 million across 1997 to 2000 and adds $628 million of debt to the balance sheet. The bulk is consolidating Chewco and JEDI, which should have been consolidated from the start.\n\nThere is no presentation of this that is not serious.",
  },
  {
    s: "Chewco — the 3% equity was never there",
    f: "ben.glisan@enron.com",
    t: ["richard.causey@enron.com"],
    d: "2001-11-05T09:15:00Z",
    folder: "sent_items",
    thread: "th-restate",
    concepts: ["spe", "restatement", "accounting", "concealment"],
    body:
      "The outside equity in Chewco was collateralised with cash reserves we provided. That means the 3% independent equity required for non-consolidation was never genuinely at risk, and Chewco should have been on the balance sheet since 1997.",
  },
  {
    s: "Gas curve for 2002 — desk positions",
    f: "john.arnold@enron.com",
    t: ["louise.kitchen@enron.com", "greg.whalley@enron.com"],
    d: "2001-06-19T13:05:00Z",
    folder: "west",
    thread: "th-gas",
    att: ["curve_2002.xls"],
    concepts: ["trading", "gas", "curve", "positions"],
    body:
      "The 2002 curve is in contango through March and the desk is long the front. Storage economics support carrying it. Risk is comfortable with the position size.",
  },
  {
    s: "Credit exposure to counterparties — weekly",
    f: "vince.kaminski@enron.com",
    t: ["greg.whalley@enron.com", "richard.causey@enron.com"],
    d: "2001-10-29T08:00:00Z",
    folder: "research",
    thread: "th-credit",
    att: ["counterparty_exposure.xls"],
    concepts: ["credit", "risk", "counterparty", "liquidity"],
    body:
      "Counterparties are reducing lines. Four of the top ten have cut available credit since the 16th and two now require cash collateral on new trades.\n\nAt this rate the trading business runs out of working capital before the end of the month regardless of what the merger does.",
  },
  {
    s: "Board presentation — related party transactions",
    f: "andrew.fastow@enron.com",
    t: ["kenneth.lay@enron.com"],
    c: ["richard.causey@enron.com", "sara.shackleton@enron.com"],
    d: "2001-02-12T10:30:00Z",
    folder: "sent_items",
    thread: "th-board",
    att: ["board_related_party.ppt"],
    concepts: ["governance", "ljm", "board", "conflict"],
    body:
      "The board deck describes the LJM arrangements at a level the audit committee has previously been comfortable with. It does not itemise my economic interest, on the basis that the waiver already covers it.",
  },
  {
    s: "RE: Board presentation — related party transactions",
    f: "kenneth.lay@enron.com",
    t: ["andrew.fastow@enron.com"],
    d: "2001-02-12T21:05:00Z",
    folder: "sent_items",
    thread: "th-board",
    concepts: ["governance", "board", "conflict", "disclosure"],
    body:
      "Itemise it. If the audit committee is approving an arrangement annually they should be approving the actual numbers, not a description of the structure.",
    quoted: "> It does not itemise my economic interest.",
  },
  {
    s: "Employee 401(k) — blackout period",
    f: "kenneth.lay@enron.com",
    t: ["greg.whalley@enron.com"],
    d: "2001-10-25T07:50:00Z",
    folder: "sent_items",
    thread: "th-401k",
    concepts: ["people", "retirement", "governance"],
    body:
      "The plan administrator change puts the 401(k) into a blackout from 26 October. Employees cannot move out of company stock during that window. Confirm the dates are unavoidable, because the optics if the stock keeps falling are extremely bad.",
  },
  {
    s: "Andersen document retention policy",
    f: "mark.taylor@enron.com",
    t: ["sara.shackleton@enron.com"],
    d: "2001-10-23T16:40:00Z",
    folder: "legal",
    thread: "th-retention-docs",
    concepts: ["legal", "audit", "documents", "compliance"],
    body:
      "Once an SEC inquiry is reasonably anticipated, the retention policy stops applying and everything is preserved. Please circulate a litigation hold to everyone on the LJM and Raptor distribution lists today.",
  },
  {
    s: "Project Summer — asset sale status",
    f: "rebecca.mark@enron.com",
    t: ["kenneth.lay@enron.com"],
    d: "2000-08-14T09:25:00Z",
    folder: "international",
    thread: "th-summer",
    att: ["project_summer_status.pdf"],
    concepts: ["international", "assets", "divestiture"],
    body:
      "The buyer group has completed diligence on the international portfolio. Pricing is below book on the Indian and Brazilian assets, which means a loss on disposal if we proceed at these levels.",
  },
  {
    s: "Dabhol — payment dispute",
    f: "rebecca.mark@enron.com",
    t: ["kenneth.lay@enron.com", "greg.whalley@enron.com"],
    d: "2001-01-22T06:15:00Z",
    folder: "international",
    thread: "th-dabhol",
    concepts: ["international", "dispute", "assets"],
    body:
      "MSEB has missed the December payment and disputes the tariff calculation. We have served notice. Realistically this asset is not saleable while the dispute is live.",
  },
  {
    s: "Weather derivatives desk — 2001 plan",
    f: "vince.kaminski@enron.com",
    t: ["louise.kitchen@enron.com"],
    d: "2000-11-20T14:00:00Z",
    folder: "research",
    thread: "th-weather",
    concepts: ["trading", "modelling", "weather"],
    body:
      "The weather book has been profitable for three years on a small capital allocation. Doubling the limit is supportable provided the correlation assumptions against the power book are re-estimated quarterly.",
  },
  {
    s: "Please review before I send this to the board",
    f: "sherron.watkins@enron.com",
    t: ["vince.kaminski@enron.com"],
    d: "2001-08-14T19:30:00Z",
    folder: "sent_items",
    thread: "th-watkins",
    concepts: ["whistleblower", "risk", "accounting", "concealment"],
    body:
      "You are the only person who has said out loud that the hedges are not hedges. Before I take this any further I want to know whether you think I am wrong about the accounting.",
  },
  {
    s: "Summary of open items for Tuesday",
    f: "tana.jones@enron.com",
    t: ["mark.taylor@enron.com", "sara.shackleton@enron.com"],
    d: "2001-11-12T17:05:00Z",
    folder: "legal",
    thread: "th-approvals",
    concepts: ["legal", "governance", "controls"],
    body:
      "Open items: litigation hold acknowledgements outstanding from 23 people, LJM approval sheets still missing for 11 deals, and the V&E file has not been indexed.",
  },
];

function idFor(i: number): string {
  return `doc-${String(i + 1).padStart(4, "0")}`;
}

export const CORPUS: MockDoc[] = SEEDS.map((s, i) => ({
  id: idFor(i),
  message_id: `<${s.thread}.${i}.${Date.parse(s.d)}@enron.com>`,
  thread_id: s.thread,
  subject: s.s,
  from: s.f,
  from_name: PEOPLE[s.f] ?? s.f,
  to: s.t,
  cc: s.c ?? [],
  date: s.d,
  folder: s.folder,
  mailboxes: Array.from(new Set([s.f.split("@")[0], ...s.t.map((x) => x.split("@")[0])])),
  attachment_names: s.att ?? [],
  duplicate_count: s.dup ?? 1,
  body: s.body,
  quoted_text: s.quoted ?? "",
  concepts: s.concepts,
}));
