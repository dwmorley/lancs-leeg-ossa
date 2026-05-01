// Custom Shiny message handlers
// Handle opening URLs in a new tab/window on the client side
console.log("handlers.js loaded");

(function() {
    // Try to register the Shiny message handler
    function tryRegisterHandler() {
        if (typeof Shiny === "undefined" || !Shiny.addCustomMessageHandler) {
            console.log("Shiny not available yet, retrying in 100ms...");
            setTimeout(tryRegisterHandler, 100);
            return;
        }

        console.log("Registering open_url handler");
        Shiny.addCustomMessageHandler("open_url", function(data) {
            console.log("open_url handler called with:", data);
            if (data && data.url) {
                console.log("Opening URL:", data.url);
                window.open(data.url, "_blank");
            }
        });
        console.log("open_url handler registered successfully");
    }

    // Start registration attempts
    tryRegisterHandler();
})();
