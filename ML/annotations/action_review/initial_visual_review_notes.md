# Preliminary visual review: nineteen train video groups

This is a review draft, not confirmed ground truth. Owner mapping: a white rectangle is an identity card; colorful rectangles are cash. No legal violation verdict is assigned and no labels in this file are enabled for training.

- `X-1.mov` (ID 1): a physical ID card appears to be presented across the desk at about 9.3-10.8 s and returned around 22.5-23.7 s. The first interval is a preliminary observed ID presentation.
- `X-2.mov` (ID 2): colored cash is placed/handled at about 9.2-15.9 s while the customer remains present. Receipt status is unresolved and the clip ends mid-interaction.
- `X-4/X-47` (IDs 4/47): a white ID card remains on the desk during a customer transition around 49-61 s; it is not cash. In the second interaction, an ID-card presentation is visible around 60.3-62.2 s and colored cash is handled around 64.5-70.5 s while the customer remains present. The operation is cut off by the clip end.
- `X-11` (ID 11): one person is at the workstation and then moves toward the glass partition/door around 11.5-17 s. No customer-side handover is identified. ID presentation and rule events remain unobservable because no complete customer operation or role is established.
- `X-13` (ID 13): corrected after the owner's clarification: the person is taking cash out of a green collection bag, not leaving cash from a previous customer. The bag is already present in the clip; colored cash is on the desk by about 30-34 s and is handled/collected around 41-49 s.

- `X-3` (ID 3): a small light rectangle moves from cashier side toward the customer around 7.5-8.0 s, so this is not a confirmed customer ID presentation. Colored cash-like rectangles are handled while the customer remains present around 12.5-16.0 s. The clip ends mid-interaction; receipt status and any later count are unobservable.
- `X-5/X-48` (IDs 5/48, same source SHA-256): the customer presents a light rectangular physical ID toward the employee around 8-16 s; the card content and completion of a formal check are not readable. No cash handover is confidently identified. The same customer stays through an employee change around 58-64 s, and the clip ends during the interaction.

- `X-8` (ID 8): one person works alone at the teller workstation, handles a small pale-blue/white rectangle, then uses a wall-side unit and opens a ledger. The small object is not confidently identifiable as cash or ID; no customer transaction or count is established.
- `X-10` (ID 10): colored cash-like bundles are present on the desk from the first frame and handled by one person around 5-8 s and 13-15.5 s. No customer is visible, but cash origin, formal count, and whether a controller is outside the camera view are unknown.

## Correction and remaining uncertainty

The earlier previous-customer-cash hypothesis for X-13 (ID 13) was wrong and has been removed. The customer-cash rules are marked not applicable to this sequence. The collection-bag inspection and controller/count checks remain unobservable: the clip does not show the bag's arrival, a complete seal/integrity check, or whether a controller is outside the camera view. Do not turn these uncertainties into a violation label.

The full clips were skimmed at 1 FPS. Candidate intervals in IDs 3 and 5/48 were rechecked at about 0.5 s, with selected native-resolution frames enlarged; the corrected bag/cash sequence in X-13 (ID 13) was rechecked at about 3 FPS. This is enough to record review candidates, not enough for hand-oscillation labels or a legal conclusion. Please verify roles and boundaries in the source video.

- `X-12.mov` (ID 12): one person works at the staff-side workstation and moves behind the glass partition around 22-42 s. No customer operation or cash is identified. Record the passage only as factual context; room identity, lock state, and policy applicability are unknown.
- `X-14.mov` (ID 14): a green zippered pouch is already on the counter at the first frame and is handled/opened; colorful cash-like rectangles appear around 35-38 s. The person then handles/arranges cash-like bundles near a desk machine around 50-118 s. The owner confirms the object is a collection bag; its arrival/acceptance check, the cash source, and whether the later handling is a formal count are not established. A figure behind the glass appears to be a reflection and is not labeled as another actor.

These two source clips have weak source labels of 0, which remain clip-level weak labels and are not used as rule-specific ground truth. Rule checks with missing sequence context remain `unobservable`; neither clip receives a legal verdict or a training label.

- `X-15.mov` (ID 15): the owner-confirmed green collection bag is already on the counter. The person opens/handles it and appears to look inside around 0-6 s, sets it down, then moves behind the glass partition around 8-20.8 s while the bag remains on the counter. This is inspection-like handling, but the acceptance start and full seal/integrity check are outside or unclear in the clip; no violation is assigned. The weak positive timestamp at 15 s is not rule ground truth.
- `X-18.mov` (ID 18): a customer-side person presents a pale blue/white rectangle around 6.75-7.75 s, labeled as a physical ID under the owner mapping. Colorful cash-like pieces are handled while the customer remains present around 9-13 s. A second person comes from behind the glass and returns a white rectangular item around 20.75-21.5 s; its function is not confirmed. No missing-receipt conclusion is made. At original 29.91 FPS, no clear repeated hand oscillation was seen during the customer's purposeful reach/receipt from 20.6-22.6 s; this is limited to that interval.

X-15 and X-18 have weak source labels of 1; these remain clip-level weak labels and are not used as rule-specific ground truth.

- `X-19.mov` (ID 19): the customer presents a pale blue/white rectangle around 6.5-8 s, treated as physical ID under the owner mapping. Cash-like notes are handled while the customer is present around 9-15 s. The customer leaves through the glass partition around 44-47 s; a pale rectangle remains on the counter in those frames, but its identity/custody is uncertain. No post-departure count or missing-receipt conclusion is labeled. Hand/wrist around 9-11 s was reviewed at source FPS but is too small/occluded to assess tremor reliably.
- `X-20.mov` (ID 20): a person opens and closes the gray cabinet around 1-5 s and handles a small item near it. The item cannot be confidently identified as a key, so the storage-keys context remains unobservable. The weak positive timestamp at 5 s is not a rule label; no policy breach is inferred.

The current draft contains nineteen train groups. Source positive labels remain weak clip-level labels, not rule-specific ground truth. All event/context training flags remain false and legal violation verdicts remain null.


## Source-label cross-check: X-21-X-29

The workbook `ML/open/open/open_labels.xlsx` was checked for each clip, including its event-second column. These binary labels are weak clip-level annotations, not rule-specific ground truth.

- `X-21.mov` (ID 21): the source says 'no violation' and gives no event second. The employee stays at the staff-side desk; no customer transaction or event from the documented candidate rules is identified. The weak negative agrees with this visual review, but is not a complete compliance negative.
- `X-22.mov` (ID 22): the source says 'violation' at 14 s. This falls during the employee's approach to and passage through the glass partition (about 13-20.75 s). The timing matches the visible movement, but `CRITERIA.md` lists cashier departure/storage-left-open behavior only as an unverified hypothesis; the destination, lock state, and applicable internal policy are not visible. The source positive is therefore not confirmed as a rule violation.
- `X-23.mov` (ID 23): the source says 'no violation' with no event second. No customer operation or documented candidate event is identified; the weak negative agrees with the visible sequence but is not a comprehensive compliance label.
- `X-24.mov` (ID 24): the source says 'violation' at 8 s. This coincides with the employee reaching the glass partition door, before passing into the adjoining area (about 5.5-13.5 s). As with X-22, the weak positive aligns with a visible action, but no rule-specific breach can be confirmed from the clip or current criteria.

Across all four clips, no ID presentation or customer hand oscillation can be assessed because no customer-facing interaction is visible. All legal verdicts remain null and all training flags remain false.

- `X-25.mov` (ID 25): source says 'no violation' with no event second. The workstation occupant moves to/behind the glass partition around 24-31 s as another person appears, then returns. This is similar partition-related movement to positive clips, so the action alone does not explain the source label.
- `X-26.mov` (ID 26): source says 'violation' at 9 s. The point falls just before the workstation occupant stands and moves toward/passes through the glass partition around 9.5-19.75 s. Negative clips X-25, X-27, and X-29 show similar movement, so the point cannot be treated as rule-specific evidence.
- `X-27.mov` (ID 27): source says 'no violation' with no event second. The occupant stands and approaches/reaches near the glass partition around 9-17 s, but a full passage is not confirmed.
- `X-28.mov` (ID 28): source says 'violation' at 7 s. The point coincides with standing and beginning to move toward the partition; the occupant passes into the adjoining area around 9-12 s. Similar movement in negative clips means the weak label does not define a reliable action class.
- `X-29.mov` (ID 29): source says 'no violation' with no event second. The occupant stands, interacts near the glass partition while another person is behind it, and returns toward the workstation; full passage is not confirmed.

The positive X-26/X-28 timestamps and negative X-25/X-27/X-29 clips show why the binary workbook label must remain separate from the observed partition action. No supported rule-specific label is assigned to these actions. The train split now has all 24 source groups reviewed; all five additions remain draft-only, with training flags false and legal verdicts null.


## Validation/test source-label cross-check: X-16, X-17, X-30, X-31

These clips retain their original validation split. Their annotations are for comparison only and will not enter training.

- `X-16.mov` (val, source no violation): a person brings the owner-confirmed green collection bag to the workstation around 4-6 s; the occupant handles/opens it afterward. Inspection-like manipulation is visible, but the seal/integrity check cannot be resolved. The weak negative does not verify the rule outcome.
- `X-17.mov` (val, source violation at 7 s): the point coincides with a person placing/handling the owner-confirmed green collection bag and the workstation occupant reaching toward it around 7-10 s. The check of seal/integrity cannot be judged at this resolution; treat as temporally aligned but not confirmed as a violation.
- `X-30.mov` (val, source violation at 13 s): another person appears by the glass partition while the workstation occupant moves near the desk. Roles and action purpose are unclear; no documented rule-specific action is confirmed.
- `X-31.mov` (val, source no violation): a person enters from the partition side and sits at the workstation. No customer transaction or documented candidate event is identified.



## Final source-label/action cross-check: remaining X-32-X-46 clips


These clips complete the 40-group queue. Their original workbook split and binary label/timestamp are preserved. Positive timestamps are compared with visible actions, but are not treated as rule-specific ground truth.


- `Х-32` (val): Workbook: violation at 5 s, during staff-side arrival/workstation approach. This does not match a documented transaction or cash/count/bag sequence; weak label only.


- `Х-33` (test): Workbook: violation at 6 s, during arrival to the staff-side workstation. No cash count, handover, bag, or customer transaction is visible.


- `Х-34` (val): Workbook: violation at 13 s, as man stands/leaves and woman reaches to terminal. Timing aligns with movement, not a confirmed rule breach.


- `Х-35` (val): Workbook: no violation/second. Customer-like service and small-item handling visible, but no specific rule breach confirmed.


- `Х-37` (val): Workbook: no violation/second. Brief interaction does not establish a rule event.


- `Х-38` (val): Workbook: violation at 33 s. New person arrives while colored cash-like rectangle is already on desk; timing fits possible prior-cash-left scenario, but source, ownership and prior operation are not visible. Not confirmed.


- `Х-39` (val): Workbook: no violation/second. Long customer-like interaction with colored rectangle visible, but no specific breach verified.


- `Х-40` (test): Workbook: violation at 17 s, during beige tote placement. No collection-bag acceptance or documented cash/count sequence.


- `Х-43` (test): Workbook: no violation/second. Only equipment handling is visible; weak negative remains clip-level.


- `Х-44` (test): Workbook: violation at 16 s, during handling of small turquoise rectangle while alone. Insufficient evidence of cash intake/count or internal count without controller.


- `Х-45` (test): Workbook: no violation/second. Equipment handling only; weak negative is not a complete compliance label.


- `Х-46` (test): Workbook: violation at 11 s, during reach near equipment; colored item already on desk. No visible client, cash count, or next transaction establishes a candidate-rule breach.


All 40 task groups have now been visually reviewed against the workbook. Every event remains draft-only (`use_as_training_label=false`), legal verdicts remain null, and the review JSON remains `draft_not_for_training`. The train/validation/test split has not changed.


## Final status completion: X-1, X-2, X-4/X-47

The workbook timestamps and action sequence were checked again for the three groups whose rule-event fields were still unreviewed in the initial template.

- `X-1.mov` (train, violation at 22 s): a physical ID presentation is visible around 9.3-10.8 s and an apparent return/handling around 22.5-23.7 s. No cash-related candidate rule event is identified. The source point aligns with the document interaction, not a confirmed rule breach. Customer hand oscillation is unobservable at this camera resolution.
- `X-2.mov` (train, violation at 10 s): the customer places colored cash around 9.5-10.5 s; the cashier handles it while the customer remains present through at least 15.9 s. The point aligns with cash acceptance. Receipt status and transaction completion are unobservable because the clip ends mid-service; no rule violation is confirmed. ID presentation and hand oscillation remain unobservable.
- `X-4.mov` / `X-47.mov` (same source, train; points at 57 s and 68 s): the first point coincides with the next customer arriving while a white physical ID remains on the desk; it is not cash. The second point coincides with colored cash handling while the current customer remains present. The first point is not a prior-cash event; the second does not establish a customer-absent count or missing receipt. Both source points remain weak clip-level labels. ID presentation is observed in the second interaction around 60.3-62.2 s. Hand oscillation is unobservable at this resolution.

This resolves the remaining `unreviewed` rule/check fields without enabling any training labels or assigning a legal verdict.


## Workbook label/action comparison for early groups

The original Excel label and event-second fields were compared against the action draft for the initial clips.

- `X-1` (positive at 22 s): the point is near an apparent ID return; no cash rule event is visible.
- `X-2` (positive at 10 s): the point aligns with cash placed by the customer and handled while the customer remains present; transaction/receipt completion is unknown.
- `X-3` (negative, no point): customer-present colored-cash handling and a small pale-item transfer are visible; no specific rule outcome is established.
- `X-4/X-47` (positive at 57 s and 68 s): 57 s aligns with the next customer arriving while the previous white ID remains on the desk; 68 s aligns with current-customer cash handling. The white item is an ID, not cash, and cash is handled with the customer present.
- `X-5/X-48`, `X-8`, and `X-10` (negative, no point): ID/customer interaction, workstation/ledger activity, and cash-like bundles handled alone are seen respectively; their source labels do not establish rule outcomes.
- `X-11` (positive at 18 s) and `X-12` (negative, no point): both show movement at/through the glass partition. The movement itself is not a supported rule label.
- `X-13` (positive at 47 s): the point coincides with cash removal from the owner-confirmed collection bag, not prior-customer cash. Bag acceptance and count context remain uncertain.
- `X-14` (negative, no point): cash-like bundles are handled without a visible customer; whether this is an internal count and whether a controller is outside frame cannot be determined.
- `X-15` (positive at 15 s): the point is near partition movement; the green bag is already present and had been handled earlier.
- `X-18` (positive at 20 s): the point coincides with a white rectangular item being returned to the customer. Its transfer is visible, but the weak source label does not specify a violation.
- `X-19` (negative, no point): customer-present ID/cash handling is visible; the later pale rectangle is not cash. No rule-specific event is established.
- `X-20` (positive at 5 s): the point aligns with closing a cabinet after handling an unidentified item; it cannot be confirmed as a key.

All original binary labels and timestamps remain in the draft as weak clip-level supervision only. None of these comparisons enabled a rule-event training label.
