(function (global) {
    function readProfile(storageKey) {
        try {
            const raw = localStorage.getItem(storageKey);
            if (!raw) {
                return { player_name: '', password: '' };
            }
            const parsed = JSON.parse(raw);
            return {
                player_name: parsed.player_name || '',
                // Do not persist password in localStorage.
                password: '',
            };
        } catch (error) {
            return { player_name: '', password: '' };
        }
    }

    function writeProfile(storageKey, playerName, password) {
        try {
            localStorage.setItem(
                storageKey,
                JSON.stringify({ player_name: playerName })
            );
            return true;
        } catch (error) {
            return false;
        }
    }

    function readValue(storageKey) {
        try {
            return localStorage.getItem(storageKey);
        } catch (error) {
            return null;
        }
    }

    function writeValue(storageKey, value) {
        try {
            localStorage.setItem(storageKey, value);
            return true;
        } catch (error) {
            return false;
        }
    }

    function setStatusText(elementId, message, isError, okColor, errorColor) {
        const el = document.getElementById(elementId);
        if (!el) return;
        el.textContent = message;
        el.style.color = isError ? errorColor : okColor;
    }

    global.GameClientCommon = {
        readProfile,
        writeProfile,
        readValue,
        writeValue,
        setStatusText,
    };
})(window);
