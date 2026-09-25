# AI eval report

- Run: 2026-09-25 15:15 IST
- App model: `gemini-3.5-flash-lite` · Judge model: `gemini-3.6-flash`
- **Passed: 22/30** · Judged: 9 · **Invented facts: 1** · p50 latency: 1.40 s

| Category | Graded by | Passed |
|---|---|---|
| summary | judge | 3/7 |
| summarize | judge | 1/4 |
| explain | judge | 3/4 |
| retrieval | free checks | 5/5 |
| missing | free checks | 4/4 |
| out_of_scope | free checks | 3/3 |
| injection | free checks | 3/3 |

## Failed or errored cases

### sum-01 (summary, EVAL-01)
- Question: (summary)
- Answer: Aarav Ramesh, a 24-year-old male, presented with pain in the lower right back tooth of three days' duration. Clinical investigation of tooth 46 revealed deep dental caries with no visible swelling, positive tenderness and percussion tests, and sensitivity to hot and cold. The diagnosis is deep dental caries with suspected pulpal involvement. Notes indicate the patient was advised further evaluatio
- judge: The summary accurately reflects the patient record with no invented facts, but it fails to briefly mention what is not recorded yet as required by the summary instructions.

### sum-04 (summary, EVAL-04)
- Question: (summary)
- Answer: Meera Nair, a 61-year-old female, presented with a loose lower denture and difficulty chewing for three months involving the mandibular edentulous ridge. Clinical findings revealed a resorbed lower ridge with an ill-fitting complete denture and a sore spot on the lower left ridge, with no tenderness present. The diagnosis is an ill-fitting mandibular complete denture due to ridge resorption. A rel
- judge failed: ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again 

### sum-06 (summary, EVAL-06)
- Question: (summary)
- Answer: A 34-year-old male presented with a four-day history of swelling on the left cheek and throbbing pain affecting tooth 36. Clinical examination revealed a grossly decayed lower left first molar with vestibular swelling and mild facial swelling, tenderness to percussion, and no response to cold sensitivity testing. The condition was diagnosed as an acute periapical abscess of tooth 36. Treatment inc
- judge: The answer invents the detail 'to percussion' which is not specified in the record under tenderness. Additionally, the summary fails to briefly state what is not recorded yet as required by the summary instructions.
- invented: to percussion

### sum-08 (summary, EVAL-08)
- Question: (summary)
- Answer: Arjun Reddy, a 40-year-old male, presented with pain and swelling behind the last lower left tooth for 5 days. Investigation of tooth 38 revealed a partially erupted tooth with an inflamed operculum, tenderness, and trismus with a 25 mm mouth opening. The condition was diagnosed as pericoronitis associated with a partially impacted tooth 38. Extraction is planned after the inflammation settles.
- judge failed: ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again 

### ovr-02 (summarize, EVAL-02)
- Question: Give me a short overview of this case.
- Answer: Priya Sharma is a 34-year-old female presenting with bleeding gums while brushing for the past two weeks. Clinical findings show generalised gingival inflammation, supragingival calculus, and bleeding on probing in the upper and lower anterior gingiva. She has been diagnosed with chronic generalised gingivitis, and scaling and polishing are scheduled alongside oral hygiene instructions.
- judge failed: ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again 

### ovr-04 (summarize, EVAL-04)
- Question: Summarize this patient.
- Answer: Meera Nair is a 61-year-old female who has had a loose lower denture and difficulty chewing for three months. Clinical findings show a resorbed lower ridge with an ill-fitting complete denture and a sore spot on the lower left ridge. The diagnosis is an ill-fitting mandibular complete denture due to ridge resorption, with a reline or new denture to be discussed at the next visit.
- judge failed: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on

### ovr-06 (summarize, EVAL-06)
- Question: What are the important findings I should highlight?
- Answer: Vikram Singh presents with a four-day history of a left cheek swelling and throbbing pain related to tooth 36. Clinical findings show a grossly decayed tooth with vestibular swelling and tenderness, along with mild facial swelling and no response to cold sensitivity testing. The diagnosis is recorded as an acute periapical abscess for tooth 36.
- judge failed: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on

### exp-01 (explain, EVAL-01)
- Question: Explain the diagnosis in simple terms.
- Answer: The patient has a deep cavity in the tooth that likely reaches the nerve inside, which is why root canal treatment and further evaluation were advised.
- judge failed: ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again 
