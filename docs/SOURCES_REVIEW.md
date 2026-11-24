

\# D06 - Sources and Licences Review



\## 1. Source inventory



The project contains 10 distinct source entries in `data/sources.csv`.



The CSV structure was validated:

\- Documents: 10

\- Unique titles: 10

\- Duplicate titles: 0

\- Missing URLs: 0

\- Missing licence entries: 0



\## 2. URL checks



Nine source URLs responded successfully during the initial HTTP check.



The Carriage by Air Act PDF on India Code timed out twice. Its availability remains unverified from the development environment.



The replacement India Code record URL must be tested separately.



\## 3. robots.txt checks



| Publisher | Result | Status |

|---|---|---|

| DGCA | HTTP 404 | Not verified |

| Ministry of Civil Aviation | HTTP 403 | Not verified |

| PIB | HTTP 200 returned an HTML error page | Not verified |

| India Code | TLS error | Not verified |



These results do not establish permission for automated access.



\## 4. Reuse and copyright



Licence entries in `data/sources.csv` are provisional usage notes.



Before downloading, storing, or displaying source content:

\- Check the publisher's current terms and copyright policy.

\- Check for third-party copyright material in each document.

\- Obtain permission where required.

\- Preserve source attribution.

\- Store only content whose reuse is permitted.



\## 5. Current limitations



\- India Code source URL requires further verification.

\- robots.txt status is unresolved for all four publishers.

\- Ministry of Civil Aviation reproduction permissions require confirmation.

\- No blanket permission for automated downloading or full-text storage has been established.



\## 6. Current decision



The source inventory and CSV structure are prepared.



Automated downloading and full-text storage must remain disabled until access and reuse permissions are verified.

## 7. Detailed robots.txt and copyright review

### robots.txt browser checks

| Publisher | Browser result | Interpretation |
|---|---|---|
| DGCA | Request cannot be processed | Inaccessible |
| Ministry of Civil Aviation | Forbidden | Access forbidden |
| PIB | Server error / 404 message | Invalid robots.txt response |
| India Code | ERR_SSL_UNRECOGNIZED_NAME_ALERT | TLS error |

These results do not establish permission or prohibition for automated downloading.


### Copyright and reuse review

The publishers' current official policy pages were reviewed.

| Publisher | Verified policy finding | Project decision |
|---|---|---|
| DGCA | Website material may be reproduced accurately with prominent source acknowledgement. Third-party copyrighted material is excluded. | Attribute DGCA and obtain permission for third-party material |
| Ministry of Civil Aviation | Materials specifically intended for download may be downloaded without specific permission. Other reproduction requires Ministry approval. | Obtain approval before reproducing other website content |
| PIB | Website material may be reproduced accurately with prominent source acknowledgement. Third-party material is excluded. | Attribute PIB and obtain permission for third-party material |
| India Code | Current website displays an all-rights-reserved notice. General reuse permission was not verified. | Seek clarification before bulk downloading, storing or reproducing content |

Official policy pages:
- DGCA: https://www.dgca.gov.in/digigov-portal/jsp/dgca/footerLink/WebsitePolicy.jsp
- Ministry of Civil Aviation: https://www.civilaviation.gov.in/index.php/hi/node/8362
- PIB: https://www.pib.gov.in/content/102_2_Copyright-Policy.aspx?lang=1&reg=30
- India Code: https://indiacode.gov.in/

These policies do not establish blanket permission for automated collection or permanent full-text storage.

---

## 8. Passenger CARs and Airline Conditions of Carriage

### Updated source inventory

The source inventory now contains 12 entries:

- 10 existing government and institutional sources.
- 1 IndiGo Conditions of Carriage source.
- 1 Air India Conditions of Carriage source.

### Airline access and reuse review

| Publisher | Source | robots.txt | Download and storage permission |
|---|---|---|---|
| IndiGo | Conditions of Carriage | Not verified | Not verified |
| Air India | Conditions of Carriage | Not verified | Not verified |

The airline URLs have been added for source tracking only.

Public availability does not establish permission for automated downloading, permanent storage, or reproduction.

### Current decision

Do not automatically download the airline documents until their access conditions and applicable reuse permissions have been checked.

The Passenger CARs and two airline conditions-of-carriage sources are now represented in the source inventory.

## 9. Development environment recheck — 2026-11-23

The source inventory contains 12 entries: 10 government/institutional sources and 2 airline sources.

Latest robots.txt checks from the development environment:

| Publisher | Observed result | Status |
|---|---|---|
| DGCA | Request cannot be processed | Unverified |
| India Code | Request timed out | Unverified |
| Ministry of Civil Aviation | HTTP 403 Forbidden | Unverified |
| PIB | HTTP 200 returned HTML instead of plain-text robots rules | Unverified |
| IndiGo | Request timed out | Unverified |
| Air India | Request timed out | Unverified |

These responses do not establish permission or prohibition for automated downloading.

No robots restrictions were bypassed. No corpus documents were downloaded during these checks.

### Collection decision

Automated collection remains paused until access rules and document reuse permissions are verified for each source. Written permission is still required where applicable, particularly for airline documents.

## 10. Browser URL verification — 2026-11-24

The 12 source URLs were checked manually in a browser.

| # | Publisher | Document | Browser observation |
|---|---|---|---|
| 1 | DGCA | Passenger Denied Boarding, Cancellation and Delay CAR | Opened |
| 2 | DGCA | Refund of Airline Tickets CAR | Opened |
| 3 | DGCA | Persons with Disability and Reduced Mobility CAR | Opened |
| 4 | DGCA | Accessibility Standards and Guidelines 2022 | Opened |
| 5 | India Code | The Carriage by Air Act 1972 | Kept loading; not verified |
| 6 | MoCA | Passenger Charter | Opened |
| 7 | PIB | Passenger Compensation Guidelines | Opened |
| 8 | DGCA | Passenger Baggage Rules | Background appeared; content kept loading |
| 9 | MoCA | Passenger Grievance | Opened |
| 10 | DGCA | Passenger Information FAQs | Background appeared; content kept loading |
| 11 | IndiGo | Conditions of Carriage | Opened |
| 12 | Air India | Conditions of Carriage | Opened |

Nine URLs opened in the browser. Three did not fully load.

These are browser observations only. They do not confirm direct-file availability, automated access permission, storage permission, or permission to reproduce content in answers.

Automated collection remains paused pending access and reuse permission verification.
