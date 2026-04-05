/**
 * ゲーム管理とSocket.io通信
 */

// グローバル変数
let socket = null;
let currentGameId = null;
let currentGameState = null;
let previousBoard = null;
let lastMovePosition = null;
let gameActive = false;
let isAIThinking = false;
let aiSearchCancelled = false;
let thinkingStartedAt = 0;
let thinkingHideTimer = null;
let currentPlayMode = 'manual';
let currentAIInfo = {
    black_ai: null,
    white_ai: null
};
let matchmakingInProgress = false;
let myPlayerName = '';
let myPassword = '';
let myAssignedSeat = null;
let myAssignedRole = null;
let isMatchCreator = false;
let opponentName = '';
const MATCH_PROFILE_KEY = 'othello-match-profile';
const GAME_MODE_KEY = 'othello-game-mode';
let gameMode = null;
let singlePlayerSeat = 'first';
let roleChoicePending = false;

/**
 * ゲーム初期化
 */
function initializeGame() {
    socket = io();
    setupSocketListeners();

    if (typeof createBoard !== 'function' || typeof updateGameState !== 'function' || typeof setAIThinking !== 'function') {
        console.error('UI layer is not loaded correctly.');
        return;
    }

    createBoard();
    setPlayMode('manual', { syncServer: false, silent: true });
}

function loadMatchProfile() {
    const profile = window.GameClientCommon.readProfile(MATCH_PROFILE_KEY);
    myPlayerName = profile.player_name;
    myPassword = profile.password;
}

function persistMatchProfile(playerName, password) {
    myPlayerName = playerName;
    myPassword = password;
    window.GameClientCommon.writeProfile(MATCH_PROFILE_KEY, playerName, password);
}

function updateMatchStatus(message, isError = false) {
    window.GameClientCommon.setStatusText('match-status-text', message, isError, '#355949', '#a93c34');
}

function updateModeStatus(message, isError = false) {
    window.GameClientCommon.setStatusText('mode-status-text', message, isError, '#355949', '#a93c34');
}

function updateSingleStatus(message, isError = false) {
    window.GameClientCommon.setStatusText('single-status-text', message, isError, '#355949', '#a93c34');
}

function setViewState(view) {
    const modePanel = document.getElementById('game-mode-panel');
    const singlePanel = document.getElementById('singleplayer-panel');
    const matchPanel = document.getElementById('matchmaking-panel');
    const board = document.getElementById('game-board-container');
    const side = document.getElementById('game-side-panel');
    if (!modePanel || !singlePanel || !matchPanel || !board || !side) return;

    modePanel.classList.toggle('hidden', view !== 'mode');
    singlePanel.classList.toggle('hidden', view !== 'single-setup');
    matchPanel.classList.toggle('hidden', view !== 'matchmaking');
    board.classList.toggle('hidden', view !== 'game');
    side.classList.toggle('hidden', view !== 'game');
}

function persistGameMode(mode) {
    window.GameClientCommon.writeValue(GAME_MODE_KEY, mode);
}

function loadGameMode() {
    const mode = window.GameClientCommon.readValue(GAME_MODE_KEY);
    if (mode === 'singleplayer' || mode === 'multiplayer') {
        gameMode = mode;
    } else {
        gameMode = null;
    }
}

function setRoleChoiceButtonsDisabled(disabled) {
    const firstBtn = document.getElementById('choose-first-btn');
    const secondBtn = document.getElementById('choose-second-btn');
    if (firstBtn) firstBtn.disabled = disabled;
    if (secondBtn) secondBtn.disabled = disabled;
}

function updateSingleSeatButtons() {
    const firstBtn = document.getElementById('single-seat-first-btn');
    const secondBtn = document.getElementById('single-seat-second-btn');
    if (!firstBtn || !secondBtn) return;
    firstBtn.classList.toggle('active', singlePlayerSeat === 'first');
    secondBtn.classList.toggle('active', singlePlayerSeat === 'second');
}

function selectSingleSeat(seat) {
    singlePlayerSeat = seat === 'second' ? 'second' : 'first';
    updateSingleSeatButtons();
}

function setGameMode(mode, { persist = true } = {}) {
    if (mode !== 'singleplayer' && mode !== 'multiplayer') {
        gameMode = null;
        setViewState('mode');
        return;
    }

    gameMode = mode;
    if (persist) {
        persistGameMode(mode);
    }

    if (mode === 'singleplayer') {
        setViewState('single-setup');
        updateModeStatus('一人プレイを選択しました');
        updateSingleStatus('先手/後手とAIモデルを選択してください');
        return;
    }

    setViewState('matchmaking');
    updateModeStatus('マルチプレイを選択しました');
    updateMatchStatus('プレイヤー名と合言葉を入力してください');
}

function toggleGamePanels(visible) {
    if (visible) {
        setViewState('game');
    } else if (gameMode === 'singleplayer') {
        setViewState('single-setup');
    } else if (gameMode === 'multiplayer') {
        setViewState('matchmaking');
    } else {
        setViewState('mode');
    }
}

function setMatchButtons(waiting) {
    const startBtn = document.getElementById('start-match-btn');
    const cancelBtn = document.getElementById('cancel-match-btn');
    if (!startBtn || !cancelBtn) return;
    startBtn.disabled = waiting;
    cancelBtn.disabled = !waiting;
}

function showRoleModal(show, timeoutSeconds = 15) {
    const modal = document.getElementById('role-modal');
    const desc = document.getElementById('role-modal-description');
    if (!modal) return;
    modal.classList.toggle('hidden', !show);
    if (show && desc) {
        desc.textContent = `部屋作成者として先攻/後攻を選んでください（${timeoutSeconds}秒以内）`;
    }
}

function requestMatchmakingStart() {
    setGameMode('multiplayer');
    const nameInput = document.getElementById('player-name-input');
    const passwordInput = document.getElementById('match-password-input');
    const playerName = (nameInput?.value || '').trim();
    const password = (passwordInput?.value || '').trim();

    if (!playerName) {
        updateMatchStatus('プレイヤー名を入力してください', true);
        return;
    }
    if (!password) {
        updateMatchStatus('合言葉を入力してください', true);
        return;
    }

    persistMatchProfile(playerName, password);
    matchmakingInProgress = true;
    currentGameId = null;
    myAssignedSeat = null;
    myAssignedRole = null;
    isMatchCreator = false;
    opponentName = '';
    setMatchButtons(true);
    updateMatchStatus('マッチング待機中です...');

    socket.emit('start_matchmaking', {
        player_name: playerName,
        password,
        game_type: 'othello'
    });
}

function requestMatchmakingCancel() {
    matchmakingInProgress = false;
    setMatchButtons(false);
    socket.emit('cancel_matchmaking', {});
}

function chooseRoleAfterMatch(role) {
    if (gameMode !== 'multiplayer') {
        return;
    }
    if (!currentGameId) {
        updateMatchStatus('対局セッションがありません', true);
        return;
    }
    if (roleChoicePending) {
        return;
    }
    roleChoicePending = true;
    setRoleChoiceButtonsDisabled(true);
    updateMatchStatus('先攻/後攻を確定しています...');
    socket.emit('choose_role_after_match', { game_id: currentGameId, role });
}

function requestSingleplayerStart() {
    const aiModelSelect = document.getElementById('single-ai-model-select');
    if (!aiModelSelect) {
        updateSingleStatus('一人プレイ設定の初期化に失敗しました', true);
        return;
    }

    setGameMode('singleplayer');
    currentGameId = `othello-single-${Date.now()}`;
    myAssignedSeat = singlePlayerSeat;
    myAssignedRole = singlePlayerSeat === 'first' ? 'black' : 'white';
    isMatchCreator = true;
    opponentName = 'AI';
    roleChoicePending = false;

    setRoleChoiceButtonsDisabled(false);
    showRoleModal(false);
    toggleGamePanels(true);
    setPlayMode('ai', { syncServer: false, silent: true });

    socket.emit('create_game', {
        game_id: currentGameId,
        game_type: 'othello',
        mode: 'singleplayer'
    });

    const aiColor = singlePlayerSeat === 'first' ? 'white' : 'black';
    socket.emit('set_ai', {
        game_id: currentGameId,
        color: aiColor,
        difficulty: 'medium',
        algorithm: aiModelSelect.value,
        depth: aiModelSelect.value === 'minmax' ? 3 : null,
        iterations: aiModelSelect.value === 'mcts' ? 100 : null,
        engine_scope: 'browser'
    });

    socket.emit('set_ai', {
        game_id: currentGameId,
        color: aiColor === 'black' ? 'white' : 'black',
        difficulty: 'medium',
        algorithm: 'none',
        engine_scope: 'browser'
    });

    socket.emit('get_ai_info', { game_id: currentGameId });
    showStatus(`一人プレイ開始: あなたは${myAssignedRole === 'black' ? '黒(先手)' : '白(後手)'}です`);
}

/**
 * Socket.io リスナー設定
 */
function setupSocketListeners() {
    socket.on('connect', () => {
        aiSearchCancelled = false;
        console.log('サーバーに接続しました');
        loadMatchProfile();
        const nameInput = document.getElementById('player-name-input');
        const passwordInput = document.getElementById('match-password-input');
        if (nameInput && myPlayerName) nameInput.value = myPlayerName;
        if (passwordInput && myPassword) passwordInput.value = myPassword;

        if (gameMode === 'multiplayer' && myPlayerName && myPassword) {
            matchmakingInProgress = true;
            setMatchButtons(true);
            updateMatchStatus('再接続中です。対局への復帰を試みています...');
            socket.emit('start_matchmaking', {
                player_name: myPlayerName,
                password: myPassword,
                game_type: 'othello'
            });
        }
    });

    socket.on('disconnect', () => {
        aiSearchCancelled = true;
        setAIThinking(false);
        updateMatchStatus('接続が切断されました。再接続を待機中です...', true);
    });

    socket.on('matchmaking_status', (data) => {
        const status = data?.status || 'idle';
        const message = data?.message || '';
        if (status === 'waiting') {
            matchmakingInProgress = true;
            setMatchButtons(true);
            updateMatchStatus(message || '相手を待っています...');
            return;
        }
        matchmakingInProgress = false;
        setMatchButtons(false);
        updateMatchStatus(message || '待機を終了しました');
    });

    socket.on('match_found', (data) => {
        currentGameId = data.game_id;
        opponentName = data.opponent_name || '';
        isMatchCreator = !!data.is_creator;
        matchmakingInProgress = false;
        setMatchButtons(false);
        updateMatchStatus(`マッチ成立: ${opponentName} と対戦します`);
    });

    socket.on('role_choice_required', (data) => {
        roleChoicePending = false;
        setRoleChoiceButtonsDisabled(false);
        const timeout = data?.timeout_seconds || 15;
        if (isMatchCreator && gameMode === 'multiplayer') {
            showRoleModal(true, timeout);
        }
    });

    socket.on('role_waiting', (data) => {
        showRoleModal(false);
        updateMatchStatus(data?.message || '部屋作成者が先攻/後攻を選択中です...');
    });

    socket.on('role_assigned', (data) => {
        roleChoicePending = false;
        setRoleChoiceButtonsDisabled(false);
        myAssignedSeat = data.your_seat;
        myAssignedRole = data.your_role;
        opponentName = data.opponent_name || opponentName;
        showRoleModal(false);
        toggleGamePanels(true);
        if (gameMode === 'multiplayer') {
            setPlayMode('manual', { syncServer: false, silent: true });
        }
        showStatus(`対戦相手: ${opponentName} / あなた: ${myAssignedRole}`);
    });

    socket.on('opponent_disconnected', (data) => {
        showStatus(data?.message || '相手が切断しました。再接続待機中です。');
    });

    socket.on('opponent_reconnected', (data) => {
        showStatus(data?.message || '相手が再接続しました。');
    });

    socket.on('match_ended', (data) => {
        roleChoicePending = false;
        setRoleChoiceButtonsDisabled(false);
        showRoleModal(false);
        toggleGamePanels(false);
        currentGameId = null;
        myAssignedSeat = null;
        myAssignedRole = null;
        gameActive = false;
        previousBoard = null;
        updateMatchStatus(data?.message || '対局を終了しました', true);
    });

    socket.on('match_error', (data) => {
        roleChoicePending = false;
        setRoleChoiceButtonsDisabled(false);
        matchmakingInProgress = false;
        setMatchButtons(false);
        updateMatchStatus(data?.message || 'マッチングエラーが発生しました', true);
        if (isMatchCreator && currentGameId && gameMode === 'multiplayer') {
            showRoleModal(true);
        }
    });

    socket.on('game_state', (state) => {
        if (!currentGameId) {
            return;
        }
        if (state.game_over) {
            setAIThinking(false);
        }
        updateGameState(state);
        socket.emit('get_ai_info', { game_id: currentGameId });
    });

    socket.on('ai_thinking', (data) => {
        if (data.game_id && data.game_id !== currentGameId) {
            return;
        }
        setAIThinking(!!data.active, data.player, data.algorithm);
    });

    socket.on('ai_info', (aiInfo) => {
        currentAIInfo = {
            black_ai: aiInfo.black_ai || null,
            white_ai: aiInfo.white_ai || null
        };

        syncAIFormFromState();

        if (currentAIInfo.black_ai || currentAIInfo.white_ai) {
            setPlayMode('ai', { syncServer: false, silent: true });
        }

        updateAIStatusDisplay();
    });

    socket.on('ai_updated', (data) => {
        currentAIInfo[data.color === 'black' ? 'black_ai' : 'white_ai'] =
            data.algorithm === 'none'
                ? null
                : {
                    algorithm: data.algorithm,
                    difficulty: data.difficulty,
                    minmax_depth: data.depth,
                    mcts_iterations: data.iterations
                };

        syncAIFormFromState();

        const colorText = data.color === 'black' ? '黒' : '白';
        if (data.algorithm === 'none') {
            showStatus(`${colorText}のAIを解除しました`);
        } else {
            const algoText = data.algorithm === 'minmax' ? 'MinMax' : 'MCTS';
            const paramText = data.algorithm === 'minmax'
                ? `depth=${data.depth ?? 3}`
                : `試行=${data.iterations ?? 100}`;
            showStatus(`${colorText}のAIを${algoText}(${paramText})に設定しました`);
        }
        updateAIStatusDisplay();
    });

    socket.on('error', (data) => {
        showStatus(`エラー: ${data.message}`);
    });
}

/**
 * プレイモード切り替え
 */
function setPlayMode(mode, options = {}) {
    const { syncServer = true, silent = false } = options;
    currentPlayMode = mode;
    const aiMode = mode === 'ai';

    const modeManualBtn = document.getElementById('mode-manual-btn');
    const modeAIBtn = document.getElementById('mode-ai-btn');
    const aiSettingsGroup = document.getElementById('ai-settings-group');
    const applyAIBtn = document.getElementById('apply-ai-btn');
    const modeDescription = document.getElementById('mode-description');
    const blackAIEnable = document.getElementById('black-ai-enable');
    const whiteAIEnable = document.getElementById('white-ai-enable');

    if (gameMode === 'multiplayer') {
        mode = 'manual';
    }

    modeManualBtn.classList.toggle('active', !aiMode);
    modeAIBtn.classList.toggle('active', aiMode);
    modeAIBtn.disabled = gameMode === 'multiplayer';
    aiSettingsGroup.classList.toggle('hidden', !aiMode || gameMode === 'multiplayer');
    applyAIBtn.disabled = !aiMode || gameMode === 'multiplayer';
    modeDescription.textContent = gameMode === 'multiplayer'
        ? 'マルチプレイ: 手動プレイのみ利用できます。'
        : aiMode
            ? 'AIプレイ: AIを使うプレイヤーを黒/白それぞれ設定できます。'
            : '手動プレイ: 人間同士で対戦します。';

    if (aiMode) {
        syncAIFormFromState();
    } else {
        blackAIEnable.checked = false;
        whiteAIEnable.checked = false;
        updateAIToggleAvailability();
        if (syncServer) {
            clearAIPlayers();
        }
    }

    if (!silent) {
        showStatus(aiMode ? 'AIプレイモードに切り替えました' : '手動プレイモードに切り替えました');
    }
}

/**
 * AI トグル可用性の更新
 */
function updateAIToggleAvailability() {
    const blackAIEnable = document.getElementById('black-ai-enable');
    const whiteAIEnable = document.getElementById('white-ai-enable');
    const blackAlgorithmSelect = document.getElementById('black-algorithm');
    const whiteAlgorithmSelect = document.getElementById('white-algorithm');

    blackAlgorithmSelect.disabled = !blackAIEnable.checked;
    whiteAlgorithmSelect.disabled = !whiteAIEnable.checked;
    updateAIParameterVisibility('black');
    updateAIParameterVisibility('white');
}

/**
 * AI パラメーター表示の更新
 */
function updateAIParameterVisibility(color) {
    const isBlack = color === 'black';
    const blackAIEnable = document.getElementById('black-ai-enable');
    const whiteAIEnable = document.getElementById('white-ai-enable');
    const blackAlgorithmSelect = document.getElementById('black-algorithm');
    const whiteAlgorithmSelect = document.getElementById('white-algorithm');
    const blackDepthGroup = document.getElementById('black-depth-group');
    const whiteDepthGroup = document.getElementById('white-depth-group');
    const blackIterationsGroup = document.getElementById('black-iterations-group');
    const whiteIterationsGroup = document.getElementById('white-iterations-group');
    const blackDepthInput = document.getElementById('black-depth');
    const whiteDepthInput = document.getElementById('white-depth');
    const blackIterationsInput = document.getElementById('black-iterations');
    const whiteIterationsInput = document.getElementById('white-iterations');

    const enabled = isBlack ? blackAIEnable.checked : whiteAIEnable.checked;
    const algorithm = isBlack ? blackAlgorithmSelect.value : whiteAlgorithmSelect.value;

    const depthGroup = isBlack ? blackDepthGroup : whiteDepthGroup;
    const iterationsGroup = isBlack ? blackIterationsGroup : whiteIterationsGroup;
    const depthInput = isBlack ? blackDepthInput : whiteDepthInput;
    const iterationsInput = isBlack ? blackIterationsInput : whiteIterationsInput;

    const usesMinMax = enabled && algorithm === 'minmax';
    const usesMcts = enabled && algorithm === 'mcts';

    depthGroup.classList.toggle('hidden', !usesMinMax);
    iterationsGroup.classList.toggle('hidden', !usesMcts);
    depthInput.disabled = !usesMinMax;
    iterationsInput.disabled = !usesMcts;
}

/**
 * AIプレイヤーをクリア
 */
function clearAIPlayers() {
    if (gameMode === 'multiplayer') {
        return;
    }
    socket.emit('set_ai', {
        game_id: currentGameId,
        color: 'black',
        difficulty: 'medium',
        algorithm: 'none',
        engine_scope: 'browser'
    });
    socket.emit('set_ai', {
        game_id: currentGameId,
        color: 'white',
        difficulty: 'medium',
        algorithm: 'none',
        engine_scope: 'browser'
    });
}

/**
 * AI フォーム状態の同期
 */
function syncAIFormFromState() {
    const blackAIEnable = document.getElementById('black-ai-enable');
    const whiteAIEnable = document.getElementById('white-ai-enable');
    const blackAlgorithmSelect = document.getElementById('black-algorithm');
    const whiteAlgorithmSelect = document.getElementById('white-algorithm');
    const blackDepthInput = document.getElementById('black-depth');
    const whiteDepthInput = document.getElementById('white-depth');
    const blackIterationsInput = document.getElementById('black-iterations');
    const whiteIterationsInput = document.getElementById('white-iterations');

    blackAIEnable.checked = !!currentAIInfo.black_ai;
    whiteAIEnable.checked = !!currentAIInfo.white_ai;

    if (currentAIInfo.black_ai) {
        blackAlgorithmSelect.value = currentAIInfo.black_ai.algorithm;
        blackDepthInput.value = currentAIInfo.black_ai.minmax_depth || 3;
        blackIterationsInput.value = currentAIInfo.black_ai.mcts_iterations || 100;
    }
    if (currentAIInfo.white_ai) {
        whiteAlgorithmSelect.value = currentAIInfo.white_ai.algorithm;
        whiteDepthInput.value = currentAIInfo.white_ai.minmax_depth || 3;
        whiteIterationsInput.value = currentAIInfo.white_ai.mcts_iterations || 100;
    }

    updateAIToggleAvailability();
}

/**
 * AI ターン処理
 */
function handleAITurn(gameState) {
    try {
        aiSearchCancelled = false;
        const jsGameState = new GameStateJS(gameState);
        const currentIsBlack = gameState.current_player === 1;
        const aiConfig = currentIsBlack ? currentAIInfo.black_ai : currentAIInfo.white_ai;

        let move = null;

        if (aiConfig) {
            if (aiConfig.algorithm === 'minmax') {
                const minmaxAI = new MinMaxAI(aiConfig.difficulty, aiConfig.minmax_depth);
                move = minmaxAI.getMove(jsGameState, () => aiSearchCancelled);
            } else if (aiConfig.algorithm === 'mcts') {
                const mctsAI = new MCTSAI(aiConfig.difficulty, aiConfig.mcts_iterations);
                move = mctsAI.getMove(jsGameState, () => aiSearchCancelled);
            }
        }

        if (aiSearchCancelled) {
            setAIThinking(false);
            return;
        }

        if (move) {
            setAIThinking(false);
            // 手を送信
            socket.emit('make_move', {
                game_id: currentGameId,
                row: move[0],
                col: move[1]
            });
        } else {
            // パスの場合もサーバーに通知
            setAIThinking(false);
            socket.emit('make_move', {
                game_id: currentGameId,
                row: -1,
                col: -1
            });
        }
    } catch (error) {
        console.error('AI 手選択エラー:', error);
        setAIThinking(false);
    }
}

window.addEventListener('beforeunload', () => {
    aiSearchCancelled = true;
});

/**
 * プレイヤーが石を置けるかどうかを判定
 */
function canPlayerMove() {
    if (!currentGameState || !gameActive) return false;

    if (myAssignedRole === 'black' && currentGameState.current_player !== 1) return false;
    if (myAssignedRole === 'white' && currentGameState.current_player !== 2) return false;

    const currentIsBlack = currentGameState.current_player === 1;
    return currentIsBlack ? !isBlackAI() : !isWhiteAI();
}

/**
 * 黒にAIが設定されているかチェック
 */
function isBlackAI() {
    return currentAIInfo.black_ai !== null;
}

/**
 * 白にAIが設定されているかチェック
 */
function isWhiteAI() {
    return currentAIInfo.white_ai !== null;
}

/**
 * ステータスメッセージを表示
 */
function showStatus(message) {
    const statusMessage = document.getElementById('status-message');
    statusMessage.textContent = message;
}

window.requestMatchmakingStart = requestMatchmakingStart;
window.requestMatchmakingCancel = requestMatchmakingCancel;
window.chooseRoleAfterMatch = chooseRoleAfterMatch;
window.toggleGamePanels = toggleGamePanels;
window.setGameMode = setGameMode;
window.requestSingleplayerStart = requestSingleplayerStart;
window.selectSingleSeat = selectSingleSeat;

/**
 * AI 状態表示の更新
 */
function updateAIStatusDisplay() {
    const aiStatusText = document.getElementById('ai-status-text');
    const blackAI = getCurrentAI('black');
    const whiteAI = getCurrentAI('white');

    let statusText = [];
    if (blackAI) {
        const algoName = blackAI.algorithm === 'minmax' ? 'MinMax' : 'MCTS';
        const paramText = blackAI.algorithm === 'minmax'
            ? `depth=${blackAI.minmax_depth ?? 3}`
            : `試行=${blackAI.mcts_iterations ?? 100}`;
        statusText.push(`黒: ${algoName}(${paramText})`);
    }
    if (whiteAI) {
        const algoName = whiteAI.algorithm === 'minmax' ? 'MinMax' : 'MCTS';
        const paramText = whiteAI.algorithm === 'minmax'
            ? `depth=${whiteAI.minmax_depth ?? 3}`
            : `試行=${whiteAI.mcts_iterations ?? 100}`;
        statusText.push(`白: ${algoName}(${paramText})`);
    }

    if (statusText.length === 0) {
        aiStatusText.textContent = 'なし';
        aiStatusText.style.color = '#666';
    } else {
        aiStatusText.textContent = statusText.join(' | ');
        aiStatusText.style.color = '#2e8b57';
    }
}

/**
 * 現在の色に対するAI設定を取得
 */
function getCurrentAI(color) {
    if (color === 'black') {
        return currentAIInfo.black_ai;
    } else {
        return currentAIInfo.white_ai;
    }
}

