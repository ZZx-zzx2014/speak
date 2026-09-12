/* Opens the administrator welcome dialog as a real modal.
 *
 * Kept in its own file so the Content-Security-Policy can keep forbidding
 * inline scripts.  ``defer`` guarantees the dialog markup exists by the time
 * this runs. */
(function () {
    'use strict';

    var dialog = document.getElementById('admin-setup');
    if (!dialog || typeof dialog.showModal !== 'function') {
        return;
    }

    dialog.showModal();

    var closeButton = document.getElementById('admin-setup-close');
    if (closeButton) {
        closeButton.addEventListener('click', function () {
            dialog.close();
        });
    }
}());
