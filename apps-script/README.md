# El Niño assistant: Google Apps Script setup

The public platform's chat box answers from EPA's approved FAQ and the platform's data. This script, run from an EPA Google account, lets it use AI as well: an AI model writes each answer from that same material. The AI key stays in EPA's account and never reaches the website. Setup takes about 20 minutes.

## What you need

- An official EPA Google Workspace account (not a personal one), so the script, key and logs belong to EPA.
- A Gemini API key from Google AI Studio (https://aistudio.google.com), made with that same account. Turn on billing for the paid tier: Google uses free-tier prompts to improve its products, and the free tier has tight limits.

## Steps

1. **Make the Sheet.** In Google Drive, create a Google Sheet named `El Niño assistant`.
2. **Add the script.** In the Sheet, open **Extensions → Apps Script**. Delete the sample code, paste in all of `Code.gs` from this folder, and save.
3. **Add the key.** In Apps Script, open **Project Settings → Script properties → Add script property**. Name it `GEMINI_API_KEY` and paste the key as its value. Save.
4. **Create the tabs.** In the editor, choose the `setup` function and press **Run**, then allow the permissions Google asks for. The Sheet now has four tabs:
   - **Rules:** how the assistant must answer.
   - **FAQ:** the 20 approved answers, copied from the website.
   - **Contacts:** agencies and numbers. Fill in a number only once EPA has confirmed it.
   - **Log:** every question asked, with time, places, answer and result.
5. **Test it.** Choose `testAnswer` and press **Run**. The execution log should show `"ok":true` and a short answer.
6. **Publish it.** Choose **Deploy → New deployment**, pick **Web app**, set *Execute as* to **Me** and *Who has access* to **Anyone**, then press **Deploy**. Copy the web app address, which ends in `/exec`.
7. **Connect the website.** Put that address between the quotes in `docs/assets/ask-config.js` (`window.LM_ASK_URL = "https://script.google.com/macros/s/.../exec";`), or send it to the site maintainer. The chat box then shows **AI answers** and offers **Answer in Liberian English**.

## Running it

- **Changing answers:** edit the Rules, FAQ or Contacts tabs. Changes reach the assistant within 10 minutes; no code or redeploy needed. Changes to the FAQ tab apply to AI answers only. To change the website's no-AI answers as well, update `docs/data/faq.json` to match.
- **Limits:** the script answers at most 30 questions a minute and 2,000 a day across all visitors. To change these, add the Script properties `PER_MINUTE` or `DAILY_LIMIT`. Over the limit, visitors get the approved answer instead.
- **Model:** the default is `gemini-3.5-flash-lite`. To use a different Gemini model, set the Script property `MODEL`.
- **Cost:** check Google's pricing page (https://ai.google.dev/gemini-api/docs/pricing) and set a budget alert in Google Cloud billing. Each answer sends about 3,000 words of rules, FAQ and data to the model.
- **Turning AI off:** empty the address in `ask-config.js`, or archive the deployment in Apps Script. The chat box falls back to approved answers.
- **After editing `Code.gs`:** choose **Deploy → Manage deployments → Edit → New version**. The address stays the same.
- **Privacy:** the Log tab holds questions as typed. Share the Sheet only with staff who review the assistant.
