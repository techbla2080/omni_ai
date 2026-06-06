// OmniAI — Google Analytics (GA4)
// Loads gtag.js and exposes window.track(name, params) for custom events.
// Measurement ID: G-NWJTVK75R7
(function () {
    var GA_ID = 'G-NWJTVK75R7';

    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);

    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    gtag('js', new Date());
    gtag('config', GA_ID);

    // Safe custom-event helper used across the app. Never throws.
    window.track = function (name, params) {
        try { window.gtag('event', name, params || {}); } catch (e) {}
    };
})();