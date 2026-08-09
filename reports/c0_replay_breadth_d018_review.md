# D018 final breadth review

Date: 2026-08-09

The clean ambiguity-safe D018-v2 run uses the same deterministic six shards and
proof corpus as D017. The detailed hand-reading observations in
`reports/c0_replay_breadth_d017_review.md` remain valid: exact repeated tactic
paths create real savings, while the largest expensive tactics are often
downstream of unique prefixes.

The final matcher changes the quantitative accounting in the conservative
direction:

- explicit fallbacks increase from 1,508 to 2,425 because duplicate
  syntax-kind profiler frames without a unique ordered alignment now fail
  closed;
- profiled reached units decrease from 32,054 to 29,011;
- no full or profile verdict changes, errors, timeouts, or missing CPU values
  occur;
- the opportunity estimate decreases from the diagnostic 6.463% to 5.911%;
- the theorem-bootstrap 95% interval is 4.964%–6.959%.

Manual reinspection of the highest-reuse theorem (`lean_workbook_plus_67496`),
the most expensive proof (`lean_workbook_plus_64419`, candidate 31), the shared
failure family (`lean_workbook_plus_61820`), and the expensive unique incorrect
proposal for `lean_workbook_plus_30281` confirms that the qualitative
interpretation is unchanged. D018 is a semantic/operational breadth gate, not
the registered complete-corpus decision. The low estimate is a strong warning,
but the full D019 census must run without changing the 15% threshold or exact
equality rule.
