function doPost(event) {
  const output = (value) => ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);

  try {
    const payload = JSON.parse(event.postData.contents);
    const expectedSecret = PropertiesService
      .getScriptProperties()
      .getProperty("EMAIL_WEBHOOK_SECRET");

    if (!expectedSecret || payload.secret !== expectedSecret) {
      return output({ ok: false });
    }
    if (!payload.to || !payload.subject || !payload.text) {
      return output({ ok: false });
    }

    GmailApp.sendEmail(
      String(payload.to),
      String(payload.subject),
      String(payload.text),
      { name: "SIMPONI" },
    );
    return output({ ok: true });
  } catch (error) {
    console.error("Email relay failed", error);
    return output({ ok: false });
  }
}