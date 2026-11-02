# C1.56 SOP alignment and statistical evidence mapping

This is a provisional alignment draft, prepared from researcher-supplied text and permitted source/documentation inspection. It contains no acoustic, thermal, survey or emergency-scenario performance results. C1.55 remains an unchanged historical protocol draft; this document supplies a revision plan and provisional SOP mapping rather than rewriting that report.

## A. Source provenance and SOP wording

The researcher supplied the SOP candidate attributed to **“final thesis bukas (4).docx”**, its questionnaire block mapping/rating scale, a manuscript discrepancy attributed to **“THESIS NI AIVAN.docx”**, and a summary of the statistician's recorded recommendations. These are **RESEARCHER-SUPPLIED SOURCE TEXT**, not independently verified DOCX/instrument/statistician-document contents. No original DOCX was opened in C1.56. Institutional approval of this wording is **NOT CONFIRMED**. Objectives in the matrix are proposed operational objectives, not quotations from an approved Objectives section.

The exact question wording is reproduced in column 2 of section C. Line wrapping is normalized and the supplied numbered subcriteria follow each question in sequence, separated by semicolons. Case, criteria names and question wording are retained. The supplied criterion blocks—not unseen item wording—support the provisional instrument mapping.

Source register:

| ID | Source | Authority and permitted use |
|---|---|---|
| R1 | Researcher's C1.56 message, main SOP candidate | Provisional wording authority for this draft only; manuscript/institution approval pending |
| R2 | Researcher's report of the second draft | Records conflict; does not supersede R1 |
| R3 | Researcher-supplied questionnaire blocks and 4-point scale | Block correspondence only; full item content, instrument validity, original files and real responses NOT AVAILABLE |
| R4 | Researcher-supplied statistician recommendation summary | Issue register; not proof that statistical recommendations were implemented |
| L1 | `docs/C1_55_acoustic_validation_protocol.md` | Existing offline protocol; hash verified before work |
| L2 | C1.43–54 reports/source and experimental contract/mapper | Engineering and mocked evidence with explicit integration limits |
| W1 | ISO official records and public terminology sources cited in E | Edition comparison; does not prove which edition the thesis cites |
| ACRA | No reference supplied or opened for this milestone | Not used; proposed headings below derive from the supplied SOPs |

## B. SOP 1 manuscript discrepancy

R1 says **“adaptive thermal thresholding”**. R2 reportedly says **“thermal detection with spatial and temporal validation”** instead. These are different methodological claims. A source branch's implementation cannot determine manuscript authority. This draft aligns provisionally to R1 and does not merge the phrases or certify either as institutionally approved.

Required resolution: researcher/adviser identifies the approved manuscript/version and exact SOP1 wording, records date/authority, then reconciles objectives, methodology, architecture, implementation evidence, instrument and Chapters 4–5. If R2 is approved, spatial/temporal validation needs explicit definitions and evidence. If R1 is approved, adaptive-threshold behavior needs explicit configuration, algorithm and authorized validation evidence. Existing source/tests do not establish either acoustic/thermal field performance claim.

## C. Complete five-SOP alignment matrix

| SOP Number | Exact Research Question | Research Objective | System Component | Data Source | Measured Variable / Indicator | Experimental Unit | Respondent Group | Evaluation Instrument | Statistical Treatment | Required Evidence | Existing Evidence Status | Remaining Gap | Chapter 4 Section | Chapter 5 Section |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | How do the researchers plan and create the proposed system entitled "IoT-Based Thermal-Acoustic Human Detection System with Machine Learning-Based Voice Activity Detection and Distress Keyword Spotting for Search and Rescue" using spectral gating, Vosk and Snowboy keyword spotting, adaptive thermal thresholding, and confidence-based fusion? | Document planning, construction, design choices and integration (proposed objective, pending manuscript approval) | Pi/ReSpeaker/MLX90640, spectral gating, Vosk/Snowboy, thermal thresholding, fusion, backend/mobile architecture | Source, architecture, configuration/provenance records, synthetic tests; authorized hardware evidence later | Implemented functions, interfaces, dependencies, offline design and verification trace | Design artifact/component; hardware configuration; software test case | Not a respondent outcome | Architecture/design checklist and traceability review | Qualitative engineering traceability; test counts with scope; no detection statistics from tests | Versioned source/config, architecture, hardware provenance, implementation/integration status and physical validation | Source and mocked evidence available; C1.51–54 observation work TEST-ONLY; physical validation NOT AVAILABLE | Spectral-gating and thermal/fusion design claims need component-specific verification; approved SOP1 wording unresolved | 4.1 | 5.1 |
| 2 | How do the researchers develop a system to address the challenges of delayed victim detection, false positives from non-human heat sources, missed detections due to background noise, and the need for offline edge deployment? | Evaluate the four stated technical challenges using objective trials (proposed objective) | VAD/KWS, thermal human detection, fusion/episode logic, offline delivery/recovery | Authorized labeled recordings/thermal scenarios and timestamped isolated system trials | Classification errors, correct-keyword detection, latency, false events, offline continuity and recovery | Frame/utterance nested in speaker/session; thermal scene/session; scripted alert episode | Not a questionnaire denominator | C1.55 protocol plus reviewed evaluation traces and trial ledger | Confusion metrics; exposure-based false-event rate; latency summaries; cluster-aware 95% CIs conditional on design; inferential tests UNDETERMINED | Human ground truth, fixed models/config, trace/reset/gap records, timing provenance, independent result review | 333 prior mocked regressions reported; actual acoustic/thermal/end-to-end measurements NOT AVAILABLE | Authorization, trial allocation, GT, resources, trace instrumentation, authority/episode policy and analysis implementation | 4.2 | 5.2 |
| 3 | How do the IT professionals evaluate the proposed system based on ISO/IEC 25010 System and Software Quality Evaluation in terms of the following criteria? 3.1 Functional Suitability; 3.2 Performance Efficiency; 3.3 Interaction Capability; 3.4 Reliability | Describe IT professional ratings for supplied SOP3 criteria (proposed objective) | Overall technical system and documented demonstration | Five real IT questionnaires: NOT AVAILABLE | Four criterion composites and item response distributions | Respondent; items repeated within respondent | 5 IT Professionals | IT items1–5 FS;6–10 PE;11–15 IC;16–20 Reliability | Counts/percentages, respondent-composite means/sample SD, ordinal summaries; inference UNDETERMINED | Approved edition/instrument, item wording, eligibility/consent, administration and genuine responses | Only researcher-supplied item-block mapping/scale available | Institutional approval, edition, item content, response data and coding plan | 4.3 | 5.3 |
| 4 | How do the rescue personnel evaluate the mobile monitoring interface of the proposed system based on ISO/IEC 25010 system and software Quality Evaluation in terms of the following criteria? 4.1 Functional Suitability; 4.2 Interaction Capability; 4.3 Reliability | Describe rescue personnel ratings of mobile monitoring (proposed objective) | Flutter mobile monitoring interface | Same eligible rescue/safety cohort questionnaires: NOT AVAILABLE | FS, IC, and mobile-interface reliability composites | Respondent; items repeated within respondent | Eligible members of the same 25 Rescue/Safety Personnel | Rescue/safety items1–5 FS;6–10 IC;11–15 mobile reliability | Respondent composites, item distributions, descriptive mean/sample SD and ordinal summaries; inference UNDETERMINED | Role eligibility for rescue evaluation, approved instrument, common demo/admin record, genuine responses | Block mapping available from researcher; no responses | Do not presume every member qualifies for SOP4; document eligibility and actual nonmissing n | 4.4 | 5.4 |
| 5 | How do the safety personnel or emergency responders evaluate the overall system alert delivery and stability based on ISO/IEC 25010 system and software Quality Evaluation in terms of the following criteria? 5.1 Reliability; 5.2 Usability | Describe safety/emergency respondent ratings of alert workflow (proposed objective) | Overall alert delivery/stability and workflow | Same eligible rescue/safety cohort questionnaires: NOT AVAILABLE | Alert-delivery reliability and alert-workflow usability composites | Respondent; paired/repeated with SOP4 where same person eligible | Eligible members of the same 25 Rescue/Safety Personnel; not an additional cohort | Rescue/safety items16–20 alert reliability;21–25 usability | Respondent composites and ordinal distributions; descriptive mean/sample SD; inference UNDETERMINED | Role eligibility for safety/emergency evaluation, approved labels/edition, actual responses | Researcher-supplied mapping only | Reality of Alert Delivery heading editorial issue; edition and eligibility unresolved; no survey data | 4.5 | 5.5 |


The entire planned cohort is exactly **5 IT Professionals + 25 Rescue/Safety Personnel = 30 unique respondents**. No rescue/safety subdivision is invented. The same eligible members of the 25 may answer both SOP4 and SOP5 through the common instrument. Their two sets of scores are repeated measurements from the same people; they do not become 50 people, nor does the combined study become 55. Record pseudonymous IDs and role eligibility once, join SOP4/5 by that ID, and report actual eligible/completed n for each block without changing the planned cohort or filling missing participants. Eligibility for both SOPs must be verified, not assumed.

Acoustic speakers, recordings, thermal scenes, frames, sessions and repeated trials are separate sample units. Their counts and sample-size justification are **NOT AVAILABLE**. The 30-person questionnaire plan supplies no acoustic sample size.

## D. Technical measurement matrix

### SOP1 engineering evidence and implementation limits

| Component/evidence | Required design evidence | Existing evidence status | Permitted thesis claim |
|---|---|---|---|
| Pi, ReSpeaker, MLX90640 | Architecture/BOM, device revision, wiring/interfaces, isolated setup record | Stack described in project policy; physical inspection not performed here | Documented design; device configuration/physical performance needs authorized evidence |
| Spectral gating/preprocessing | `raspberry_pi/kws/noise_suppressor.py`, pipeline diagram, fixed settings, before/after controlled traces | Source available; no acoustic effect measured | Algorithm implementation/design, not improved recall/noise suppression performance |
| Vosk/Snowboy | `kws_alert_dual.py` worker, alias/config, partial/final/reset and detection-index mapping | Existing runtime source plus mocks; config confidence is application-supplied | Source behavior and synthetic reproducibility; no accuracy claim |
| openWakeWord/VAD | `audio_preprocessor.py` output/config, actual model provenance | Interface inspected in earlier work; actual models not read/inferred | Additional engine interface exists; does not replace R1's Vosk/Snowboy wording |
| Adaptive thermal thresholding | `thermal_confidence.py`, precise threshold rule/config and scenario labels | Source exists; manuscript-method match and physical trial evidence pending | Document the implemented rule after code-level mapping; do not assert validated adaptation |
| Confidence-based fusion | Decision/dispatcher contracts, evidence provenance, cancellation and thermal association | Current runtime logic exists; risks identified; observation/episode reference work remains disconnected | Describe current design/defects and test-only proposals distinctly |
| Pure observation/mapper | `experiments/recognition_observation_contract.py`, `experiments/offline_recognition_mapper.py` | TEST-ONLY VERIFIED in prior milestones; no production imports/wiring | Synthetic contract compatibility only |
| Offline backend/mobile integration | Backend persistence/idempotency, WebSocket/replay/ACK and Flutter lifecycle diagrams/tests | Source and mocked components exist; physical end-to-end validation NOT AVAILABLE | Engineering integration evidence with hardware/acoustic limits |

### SOP2 technical outcomes

| Challenge / indicator | Target / evaluation unit | Ground truth and data | Required measurement / gap |
|---|---|---|---|
| Delayed victim detection | Stage-specific capture→detection→classification→delivery; scripted trial | Common-clock timestamped events and approved reference onset | Latency distributions; field “victim detection delay” cannot be inferred from software timing alone |
| Non-human heat false positives | Human versus non-human thermal frame/scene | Independently verified human/empty/hot-object scenes, repeated by scene/session | Thermal confusion matrix and false-event exposure; frame dependence documented |
| Noise-related missed detections | Correct keyword per utterance, stratified by noise/distance | Authorized positive/negative speech, exact transcripts/onsets, speaker/session IDs | Exact-keyword recall/FNR, wrong-keyword errors, noise strata and denominators |
| Offline edge operation | Isolated system session / predefined task | Recorded network isolation, no cloud/model download, local delivery/recovery prerequisites | Completion/failure counts, resources, accepted-event recovery; no assumption that disconnected mobile networking always works |
| VAD | Speech/non-speech frame and utterance | Human activity boundaries, frozen frame/hop labeling rule | Frame matrix plus utterance summaries; full VAD trace instrumentation missing |
| KWS | Each keyword one-versus-rest; utterance | Human verified phrase labels; frozen 17-phrase inventory | Exact-keyword matrix and any-distress matrix reported separately |
| Thermal/voice fusion | Controlled labeled event/trial | Linked voice/thermal IDs, synchronized timestamps, approved decision policy | Classification and escalation traces; episode/association/authority UNRESOLVED |
| Event delivery/recovery | Immutable logical alert event / scripted episode | Disposable backend/test-client ledger and independent expected outcome | Retry attempts, unique IDs, duplicates, client presentation/ACK, recovery; physical audibility measured separately if authorized |

### Exact technical results templates (all measurement cells unfilled)

Confusion matrix:

| Actual Class | Predicted Positive | Predicted Negative | Total |
|---|---|---|---|
| Actual Positive | TP = [INSERT VALUE] | FN = [INSERT VALUE] | TP + FN = [INSERT VALUE] |
| Actual Negative | FP = [INSERT VALUE] | TN = [INSERT VALUE] | FP + TN = [INSERT VALUE] |

Classification metrics:

| Component | Evaluation Unit | N Positive | N Negative | TP | FP | TN | FN | Accuracy (%) | Precision (%) | Recall (%) | Specificity (%) | F1-Score | False Positive Rate (%) | False Negative Rate (%) | 95% Confidence Interval | Evidence Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [INSERT COMPONENT] | [INSERT UNIT/TARGET/SPLIT] | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | No valid trials |

F1 is a dimensionless proportion, not percent. The single CI column must name the metric it refers to; it must not suggest one interval covers every metric. Add a companion long-form table: `Component, Evaluation Unit, Target, Split, Metric, Estimate, Denominator, CI Lower, CI Upper, CI Level, CI Method, Cluster Unit, Missing/Excluded N, Evidence Status`. CI Level is 95% for the requested tables; CI methods remain conditional on the actual design.

Latency:

| System Stage | Scenario | N Trials | Mean Latency (ms) | Standard Deviation (ms) | Median (ms) | P90 (ms) | Minimum (ms) | Maximum (ms) | Measurement Method | Evidence Status |
|---|---|---|---|---|---|---|---|---|---|---|
| [INSERT STAGE] | [INSERT SCENARIO] | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | [INSERT CLOCK/TRACE METHOD] | No valid timing trials |

Thermal and fusion:

| Scenario | Ground Truth | Thermal Prediction | Acoustic Prediction | Fusion Decision | TP | FP | TN | FN | Escalation Latency (ms) | Evidence Status |
|---|---|---|---|---|---|---|---|---|---|---|
| [INSERT SCENARIO] | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Policy/trials unavailable |

One row must declare its classification target and unit, using a scenario key/companion manifest. Counts across repeated frames and episodes cannot be mixed. Escalation latency requires an explicitly linked positive thermal observation and an accepted distinct critical event in a common clock domain. Missing IDs/timestamps imply N/A, not zero.

## E. ISO/IEC 25010 questionnaire mapping

**EDITION VERIFICATION REQUIRED.** The researcher has not supplied the thesis's exact ISO edition citation. The public [ISO 2011 model terminology](https://www.iso.org/obp/ui/?_escaped_fragment_=iso%3Astd%3Aiso-iec%3A25010%3Aed-1%3Av1%3Aen) includes Functional Suitability, Performance Efficiency, Reliability and Usability. The [ISO 2023 product-model record](https://www.iso.org/standard/78176.html) identifies the revised edition. ISO's public [25023 draft introduction](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso-iec%3A25023%3Adis%3Aed-1%3Av1%3Aen) describes the replacement of Usability by Interaction Capability in the revised product model. The draft is terminology corroboration, not an approved thesis citation or substitute for the chosen normative edition. Sources consulted 2026-11-02; no paid standard or original thesis was accessed.

| Supplied criterion | 2011 product terminology | Revised 2023 terminology issue | Draft action |
|---|---|---|---|
| Functional Suitability | Present | Present | Retain supplied label; verify chosen edition and actual items |
| Performance Efficiency | Present | Present | Retain; subjective ratings cannot establish measured latency/resource use |
| Interaction Capability | Not the 2011 product characteristic name | Revised product-model terminology | Do not silently relabel; verify edition and conceptual mapping |
| Reliability | Present | Present | Retain; survey reliability ratings differ from event delivery reliability and instrument consistency |
| Usability | 2011 product characteristic | Revised model uses Interaction Capability; quality-in-use scope requires its own citation/mapping | Retain SOP5 wording pending approval; do not assert all five supplied labels form one edition's product model |

The mixed vocabulary is a reconciliation issue, not proof of an invalid study or an approved standards mapping. Obtain the cited edition and approved instrument; map each item's actual wording to the selected construct. Do not claim ISO certification or validated content merely from block titles.

Provisional questionnaire summary templates:

| SOP | Respondent Group | ISO/IEC 25010 Criterion | Item Numbers | N Respondents | Mean | Standard Deviation | Verbal Interpretation | Rank | Evidence Status |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 5 IT Professionals planned | Functional Suitability | 1–5 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses not supplied |
| 3 | Same 5 IT Professionals | Performance Efficiency | 6–10 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses not supplied |
| 3 | Same 5 IT Professionals | Interaction Capability | 11–15 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses not supplied |
| 3 | Same 5 IT Professionals | Reliability | 16–20 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses not supplied |
| 4 | Eligible members of 25 Rescue/Safety Personnel | Functional Suitability | 1–5 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses/eligibility not supplied |
| 4 | Same eligible cohort | Interaction Capability | 6–10 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses/eligibility not supplied |
| 4 | Same eligible cohort | Reliability of Mobile Monitoring Interface | 11–15 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses/eligibility not supplied |
| 5 | Eligible members of same 25 Rescue/Safety Personnel | Reliability of Alert Delivery | 16–20 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Supplied original heading “Reality of Alert Delivery” requires editorial approval |
| 5 | Same eligible cohort | Usability of Alert Workflow | 21–25 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | Responses/eligibility not supplied |

Original questionnaire files are unchanged and were not opened. The proposed “Reliability” heading interpretation above comes from the supplied intended block mapping; do not apply that editorial correction to the source without approval. No item-level content validity conclusion is possible from item ranges alone.

Scale coding is exactly **4 Strongly Agree; 3 Agree; 2 Disagree; 1 Strongly Disagree**. Those are response anchors, not approved bands for interpreting criterion means. Verbal-interpretation cutoffs and ranking conventions require approval; none are invented. If ranking is retained, preregister direction and tie rule and rank only comparable criteria within the same cohort/construct context. Do not rank IT and rescue/safety means together as if the instruments/roles were equivalent.

## F. Statistical treatment and F1 audit

### Formulas and conventions

Accuracy = `(TP+TN)/(TP+FP+TN+FN)`; precision = `TP/(TP+FP)`; recall/sensitivity = `TP/(TP+FN)`; specificity = `TN/(TN+FP)`; F1 = `2TP/(2TP+FP+FN)`; FPR = `FP/(FP+TN)`; FNR = `FN/(FN+TP)`. Multiply rates by 100 only in percent columns. A zero denominator yields N/A (`null`), never a fabricated zero. Missing ground truth is excluded from binary denominators with counts/reasons; missing engine output is not a true negative. A valid trial with no target detection can be an FN if the positive reference label and trial completeness are established; unobserved/failed trials require a declared failure/missing-data analysis, not silent recoding.

### Actual helper reproduction using synthetic counts only

C1.56 AST-extracted and executed only `_safe_divide` and `compute_binary_metrics` from `raspberry_pi/kws/evaluate_keyword_models.py` against constructed label/score dictionaries. No runtime application module, recordings, models or database was imported. The numeric score values 0/1 and helper threshold 0.5 encode binary synthetic predictions, not a new detector threshold.

| TP | FP | TN | FN | Existing precision | Existing recall | Existing helper F1 | Direct-formula F1 |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | N/A | 0 | N/A | 0 |
| 0 | 1 | 0 | 0 | 0 | N/A | N/A | 0 |
| 0 | 0 | 1 | 0 | N/A | N/A | N/A | N/A |
| 0 | 0 | 0 | 0 | N/A | N/A | N/A | N/A |
| 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1 | 1 |
| 2 | 1 | 3 | 1 | 0.666667 | 0.666667 | 0.666667 | 2/3 (round only for display) |

The discrepancy is proven for the first two cases: undefined precision/recall does not imply undefined direct F1 when `2TP+FP+FN>0`. Proposed correction, **not applied**: derive F1 directly from integer counts through safe division; compute accuracy and explicit accuracy/F1 denominators; calculate metrics at full precision and round only output presentation. Preserve existing unrelated fields and distinguish recording-level false-positive rate per hour from event-level false alarms per hour.

Acceptance gate for a future separately scoped evaluator change: deterministic test cases above plus all-zero/no-positive/no-predicted-positive cases, asymmetric counts, unrounded calculations, accuracy/denominator fields, output compatibility, invalid/missing prediction handling, and exact event versus recording denominator checks. First demonstrate current discrepancies, then verify direct-count outputs and unchanged unrelated fields. No metric-helper or runtime code was changed here. A separate persistent regression file was unnecessary for this report-only audit; the table and extraction recipe specify the future cases. The prior 333-test mocked baseline was not rerun and no acoustic accuracy result is inferred.

### Design-dependent statistical plan

| Outcome | Design / observation unit | Independence / repetition | Descriptive treatment | Inferential method | 95% interval / assumptions |
|---|---|---|---|---|---|
| Per-keyword/VAD classification | Frozen labeled frame or utterance; paired recordings for future before/after study | Frames within utterance; utterances within speaker/session | Counts, denominators, per-keyword and any-distress matrices; strata and missingness | UNDETERMINED until allocation, independence and paired design fixed | Wilson proportion interval only for genuinely independent binary units; otherwise speaker/session-cluster resampling or model-based interval must be justified. Do not use frame n as independent n. |
| Thermal classification | Labeled thermal frame/scene under frozen conditions | Frames repeated within scene/person/session | Matrix by hot-object/empty/human condition; scene-level summaries | UNDETERMINED | Independent-scene intervals or design-respecting cluster method; scene selection/GT, cluster count and dependence checks required |
| False alert event rate | Count of events during negative exposure | Events may cluster by session/noise/engine | Count and negative hours; count/hour; repeat and retry IDs separately | UNDETERMINED | Poisson interval only if rate/independence assumptions justified; overdispersion/clustering may require another count model or cluster method |
| Stage latency | Correct event pairs in common clock; paired when same trial used across configurations | Repeated trials within speaker/session/device | Mean, sample SD, median, p90, min/max and valid/missing n | UNDETERMINED | No automatic normal/t interval. Review skew, outliers, synchronization, censoring and clusters; design-respecting resampling requires adequate independent clusters |
| Fusion/escalation/recovery | Scripted episode with explicit expected decision/event IDs | Repeated evidence and concurrent interleavings within episode | Outcome counts, duplicate counts, stage latency, trace review | UNDETERMINED | Approved episode/authority mapping, timing and missingness required before any performance CI |
| SOP3 ratings | Each IT respondent's item/block responses | 20 repeated items within each of 5 people | Item frequencies/proportions, median/IQR; proposed block mean/sample SD across respondent composites | UNDETERMINED; no routine group test from n=5 | Population inference not established by this cohort; do not assume normality or independent items. No CI or coefficient without design and statistician review |
| SOP4/5 ratings | Each eligible member of same 25 cohort | 25 repeated items; SOP4/5 overlap paired by person | Same ordinal/item and block descriptive plan; actual valid n per criterion | UNDETERMINED; do not run independent-group comparisons on overlapping respondents | Sampling method, construct/item comparability, missingness, role overlap and clustering require review |

For complete 5-item blocks, proposed respondent composite `c_i = sum(x_ij)/5`; criterion mean `mean(c_i)` over actual eligible complete respondents; sample SD `sqrt(sum((c_i - mean(c))^2)/(n-1))` if n>1, otherwise N/A. Use complete blocks under this draft's conservative missing-data proposal; report missing items/blocks and actual n and seek approval before administration. Do not impute missing values or convert them to 0. Item mean is `sum(k*f_k)/sum(f_k)` over valid ratings, with SD across respondents. Do not pool five item answers as five independent people or use pooled item SD as respondent-composite SD. No mean, SD, rank or interpretation is computed until genuine responses and approved coding are available.

Four-point individual items are ordinal. Report frequency distribution and median/IQR alongside any proposed means; treating a multi-item composite as approximately interval needs construct and scoring justification. Reliability of the technical system, subjective Reliability ratings, and a questionnaire internal-consistency coefficient are different claims. No alpha/omega, reliability coefficient, p-value, effect size, power result or sample-size justification is calculated or asserted. Small respondent groups constrain psychometric and population claims; approval by a statistician remains necessary.

Latency definitions: onset-based detection latency is first correct detection minus human-verified keyword onset; separately label recording-start latency if onset is absent. P90 follows the existing replay convention `sorted_values[floor(0.9*(n-1))]` for continuity with C1.55. Mean/min/max/median require nonempty valid observations; sample SD requires n>1. Missing or cross-clock timestamps produce N/A. Report detected-trial latency alongside FN/failure/missing counts to avoid a favorable “successful trials only” latency claim. Escalation uses accepted distinct critical event time minus explicitly associated positive thermal evidence time, contingent on an approved association policy.

## G. Proposed Chapter 4 headings

Use the supplied SOP order; labels below are proposed structure, not completed results. No ACRA document was used.

- **4.1 SOP1 — Planning, Design and Construction of the Proposed System.** Architecture, hardware/software choices, spectral-gating/Vosk/Snowboy/thermal/fusion design, offline paths, implementation status and traceability. Label the manuscript thermal-method discrepancy.
- **4.2 SOP2 — Objective Technical Evaluation of Detection, False Positives, Noise Robustness and Offline Operation.** 4.2.1 engineering/mocked regression evidence; 4.2.2 authorized acoustic/VAD/KWS trials; 4.2.3 authorized thermal/fusion scenarios; 4.2.4 stage latency/offline delivery/recovery. Mark uncollected tables NOT AVAILABLE.
- **4.3 SOP3 — IT Professional Evaluation:** Functional Suitability, Performance Efficiency, Interaction Capability, Reliability, with actual valid n from the 5-person group.
- **4.4 SOP4 — Rescue Personnel Evaluation of the Mobile Monitoring Interface:** Functional Suitability, Interaction Capability and Mobile Interface Reliability, using eligible responses from the same 25-person cohort.
- **4.5 SOP5 — Safety/Emergency Personnel Evaluation of Alert Delivery and Stability:** Alert Delivery Reliability and Alert Workflow Usability, using eligible responses from that cohort without double counting.

Every result table must state evidence class: engineering artifact, mocked software regression, actual authorized acoustic/thermal/system trial, or questionnaire response. A passing mocked test is not detection accuracy. Questionnaire ratings do not establish measured model recall or physical siren reliability.

## H. Proposed Chapter 5 headings

- **5.1 Summary and Conclusions for SOP1 — System Planning and Construction.** State only supported design/implementation findings; retain unresolved manuscript authority and integration limitations.
- **5.2 Summary and Conclusions for SOP2 — Objective Detection and Offline-System Performance.** Link each conclusion to actual technical tables and conditions; no performance conclusion until valid trials exist. Discuss scope and generalization to rescue conditions.
- **5.3 Summary and Conclusions for SOP3 — IT Professional Evaluation.** Support with actual responses, approved scoring and small-cohort limitations.
- **5.4 Summary and Conclusions for SOP4 — Mobile Monitoring Evaluation by Eligible Rescue Personnel.** Link to corresponding mobile-interface criteria and actual valid n.
- **5.5 Summary and Conclusions for SOP5 — Alert Delivery/Stability Evaluation by Eligible Safety/Emergency Personnel.** Link to alert reliability/usability ratings and distinguish these from measured event reliability.
- **5.6 Limitations and Recommendations.** Cross-reference unresolved authority, acoustic/hardware validation, data/role sampling, repeated measures, edition/wording, privacy, and future separately approved experiments. No deployment recommendation from mocks alone.

The summary/conclusion pairs should mirror SOPs 1–5 even if the institution later requires separate Summary and Conclusions headings. Do not write favorable findings or generic “effective” conclusions into placeholders.

## I. Evidence gaps and thesis-defense risks

| Recorded recommendation / issue | Required resolution | Status |
|---|---|---|
| SOP/objective/instrument alignment | Approve exact SOPs/objectives, full item wording, edition and row-level content mapping | Provisional matrix only |
| Conflicting respondent allocations | Approved plan and unique-ID register preserves 5+25=30; eligibility overlaps documented | Arithmetic and provisional mapping resolved here; actual administration NOT AVAILABLE |
| ISO edition | Approve citation and resolve mixed Interaction Capability/Usability terms | EDITION VERIFICATION REQUIRED |
| SOP1 wording | Researcher/adviser selects authoritative manuscript | UNRESOLVED |
| Trial allocation and ground truth | Approved sampling/allocation, consent/labels/transcripts/onsets, independent adjudication | NOT AVAILABLE |
| Repeated speakers/trials | Freeze cluster IDs and splits; match interval/inferential method to design | UNDETERMINED |
| Confidence intervals/reporting rules | Supply valid measurements, approved design and analysis implementation | Formulas/templates only; F1 helper gap remains |
| Generalization | Describe sampled speakers/scenes/devices/conditions and limits; avoid real-rescue efficacy claims | No field evidence |
| Questionnaires | Original approved item text, administration and 5/25 actual responses | NOT AVAILABLE; no survey results |
| Runtime safety | Resolve provisional authority, episode boundaries, thermal association, critical event identity and recovery policy | BLOCKED; experimental work disconnected |

The statistician's recommendations remain an issue register. This draft does not certify implementation of them. Source-code existence, test-only contract behavior and prior mocked test counts are not evidence of acoustic accuracy, reduced delays or field rescue outcomes.

## J. Independent read-only review

A separate read-only reviewer checked SOP/questionnaire correspondence, unique respondent accounting and eligibility, manuscript conflict, edition uncertainty, F1/count formulas, repeated measures, Chapter 4–5 structure, unsupported results/thresholds and provenance. No substantive alignment or statistical defect was found. The reviewer requested replacing the draft's review/final-verification placeholders with completed findings; those report-only corrections are recorded here and in K. The reviewer inspected safe helper AST source and ran no tests or inference. Full item content validity, institutional approval and statistical design remain unresolved as stated above.

## K. Git and backup preservation

Preflight verified all seven existing checksum manifests (41, 8, 10, 8, 10, 9 and 8 entries) and all 29 cumulative C1.43–54 source artifacts against recorded size/hash/mode. C1.55 was verified at SHA-256 `47581a0779f5181b542f162a7a53e7a1f914870101f7f18098bf3ebece8420f4`.

New incremental backup: `/home/thesis/offline-work-backups/C1_56_incremental_20261102T065340.946724Z`.
It contains six checksummed artifacts including the C1.55 report archive, raw recovered copy, inventory, HEAD, checkout states and RESTORE instructions. Recovery is 1/1 byte-exact; SHA256SUMS digest is `f4981cc259a9ff866c8f4d5a0e5ec6cf0134d24673ce26c563d42af0687bcaca`. No existing backup was altered. Source inventory and prior manifest digests are stored in its inventory.

Development branch is `development/c1-43-c1-47-recognition-safety`, HEAD `8a44f109fae8adb4b7daa833c15548b56ccd2452`. Final comparison confirmed identical production/evaluation branch, HEAD and Git status; evaluation remains clean and production tracked files remain clean with its pre-existing untracked status untouched. All 30 prior artifacts (29 plus C1.55) match saved hashes; exactly this report is the new worktree path and the staged diff is empty. Existing backup manifests/artifacts passed checksum verification, including the unchanged failed C1.48 attempt; the new C1.55 archive/recovery also matches sizes, modes and bytes. No existing metric helper or application runtime file was edited. No original questionnaire/manuscript, recording/model content, credentials, database or alert history was opened; no acoustic evaluation, service/device/configuration action, staging, commit, push or forbidden Git synchronization was performed.

## L. C1.57 acoustic evaluation readiness gates

C1.55 scenarios map provisionally to SOP2 as follows:

| C1.55 scenario | SOP2 technical question | Missing evidence / justified addition | Execution status |
|---|---|---|---|
| Partial tulong→tulog; genuine partial-only distress | Noise-related misses/false positives and latency | Human transcript/onset; raw Vosk status/revision/reset/generation and packet/gap traces. Current worker resets after a match, so post-reset text is not the earlier candidate's final; no-reset comparisons require separate evaluation-only design | BLOCKED |
| Final keyword and independent Snowboy/openWakeWord help | Exact-keyword recall and fusion suppression | Positive/negative trials, distinct speaker/session IDs, fixed aliases/models, per-engine outcomes including missing confidence | BLOCKED |
| Ordinary speech, noise, distance, silence | False activation and noise-related misses | Verified negative/positive labels, noise/environment/distance metadata, ground truth and trial allocation | BLOCKED |
| VAD operation | Missed speech and processing pipeline | Human speech boundaries, frame/hop policy and complete VAD traces | BLOCKED |
| Thermal-positive advisory escalation | Heat false positives and thermal/voice decision fusion | Human/hot-object/empty scenes, target conditions, synchronized thermal/voice IDs, approved association/critical-event rule | BLOCKED |
| Repeated scores/duplicate events | Stable offline event handling | Observation/candidate/episode/event IDs, preregistered scripted trials and expected event counts; no invented release timeout | BLOCKED |
| Missing output, failure and restart | Offline continuity and recovery | Explicit health/generation, complete trial trace, gap/failure accounting and resource monitoring | BLOCKED |
| Backend interruption/replay, Flutter presentation/acknowledgement | Alert delivery and recovery | Disposable store/test client/network, immutable ID ledger and all stage timestamps; physical audibility only with separate approval | BLOCKED |

The next executable milestone should first complete **evaluation-only metric/trace readiness**: separately authorize a small source/test scope for direct-count F1/accuracy/denominators and VAD/Vosk reset-gap trace fixtures, independently review it, and approve the exact SOP/edition/instrument/preregistration. Actual collection/inference remains blocked until consent/ground truth, model licenses/provenance, trial design, resource limits and isolated hardware/network/storage gates are satisfied. Preserve the 17 phrases and the 5+25 cohort. Do not alter swap, Docker, services or boot settings to bypass resource gates. No new acceptable accuracy, latency target, alarm threshold, confirmation timeout, episode rule or association duration is selected here.

Final decisions:

- **SOP ALIGNMENT DRAFT COMPLETE: YES** — all five supplied candidates and instrument blocks mapped provisionally.
- **APPROVED SOP WORDING CONFIRMED: NO**.
- **STATISTICAL METHODS READY: NO** — descriptive formulas/templates ready; design, data, edition, scoring approval, intervals and inferential selection remain incomplete.
- **ACOUSTIC EVALUATION AUTHORIZED: NO**.
- **RUNTIME INTEGRATION READY: NO**.
- **PRODUCTION DEPLOYMENT READY: NO**.
