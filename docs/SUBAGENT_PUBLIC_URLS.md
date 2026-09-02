# Bounded sub-agent public URL opening

This capability opens a small, reviewed list of public websites in the
computer's default browser. It is deliberately not browser automation and is
not a way for a sub-agent to control a browser.

## End-to-end flow

1. Build a sub-agent with the `open_public_urls` capability. It still receives
   no arbitrary tools, filesystem access, shell access, or nested delegation.
2. Put the reviewed URLs in one `.txt` or `.md` file inside the configured
   workspace. Every active line must use this exact format:

   ```text
   # Optional comment
   OPEN https://example.com/research
   OPEN https://www.python.org
   ```

3. Delegate with an explicit file-only instruction:

   ```text
   Have BrowserReviewAgent open public URLs listed in browser_urls.txt
   ```

4. Jarvis validates the workspace path, every line, every URL, and the public
   network address before it opens any tab. A later invalid line stops the
   entire request before a browser is opened.
5. Jarvis reports the URLs that were actually handed to the default browser.

## Enforced limits

- Maximum five URLs per request.
- Only `http` and `https` public URLs are accepted.
- No login, search, click, scrolling, form filling, upload, download,
  submission, message sending, payments, account access, or website scraping.
- Requests such as `Open Google and find the best price` are rejected. The
  sub-agent cannot use a general browser or make web decisions.
- The parent tool—not the local model—validates and opens the URLs. A model
  cannot claim an external action succeeded.
