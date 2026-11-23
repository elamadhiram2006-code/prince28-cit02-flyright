

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
