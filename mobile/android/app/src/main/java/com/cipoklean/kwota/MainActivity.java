package com.cipoklean.kwota;

import android.app.DownloadManager;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.WebView;
import android.widget.Toast;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // The WebView ignores downloads by default, so the quote PDF would never save.
        // Hand http(s) downloads to Android's DownloadManager; the file lands in Downloads.
        WebView webView = getBridge().getWebView();
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (url == null || !(url.startsWith("http://") || url.startsWith("https://"))) {
                Toast.makeText(this, "Could not save this file", Toast.LENGTH_SHORT).show();
                return;
            }
            String name = URLUtil.guessFileName(url, contentDisposition, mimeType);
            if (name.endsWith(".bin") && url.contains(".pdf")) {
                name = name.replace(".bin", ".pdf");
            }
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setMimeType(mimeType);
            String cookies = CookieManager.getInstance().getCookie(url);
            if (cookies != null) {
                request.addRequestHeader("Cookie", cookies);
            }
            request.addRequestHeader("User-Agent", userAgent);
            request.setTitle(name);
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            dm.enqueue(request);
            Toast.makeText(this, "Saving " + name + " to Downloads", Toast.LENGTH_SHORT).show();
        });
    }
}
