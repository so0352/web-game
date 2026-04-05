/**
 * UI操作とDOM操作
 */

/**
 * AI が思考中であることを表示
 */
function setAIThinking(active, player = null, algorithm = null) {
    const thinkingIndicator = document.getElementById('thinking-indicator');
    const thinkingText = document.getElementById('thinking-text');

    if (active) {
        if (thinkingHideTimer) {
            clearTimeout(thinkingHideTimer);
            thinkingHideTimer = null;
        }
        isAIThinking = true;
        thinkingStartedAt = Date.now();
        thinkingIndicator.classList.remove('hidden');
    } else {
        if (!isAIThinking) {
            thinkingIndicator.classList.add('hidden');
            return;
        }

        const elapsed = Date.now() - thinkingStartedAt;
        const remaining = Math.max(0, 500 - elapsed);
        thinkingHideTimer = setTimeout(() => {
            isAIThinking = false;
            thinkingIndicator.classList.add('hidden');
            thinkingHideTimer = null;
        }, remaining);
        return;
    }

    const playerText = player === 'black' ? '黒' : player === 'white' ? '白' : 'AI';
    const algorithmText = algorithm === 'minmax'
        ? 'MinMax'
        : algorithm === 'mcts'
            ? 'モンテカルロ'
            : 'AI';
    thinkingText.textContent = `${playerText}AI (${algorithmText}) が思考中です...`;
}

/**
 * ゲームボードを作成
 */
function createBoard() {
    const gameBoard = document.getElementById('game-board');
    gameBoard.innerHTML = '';
    for (let row = 0; row < 8; row++) {
        for (let col = 0; col < 8; col++) {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.dataset.row = row;
            cell.dataset.col = col;
            cell.addEventListener('click', handleCellClick);
            gameBoard.appendChild(cell);
        }
    }
}

/**
 * セルクリックハンドラー
 */
function handleCellClick(e) {
    if (!gameActive || !currentGameState) {
        showStatus('ゲームが開始されていません');
        return;
    }

    // 現在手番の色がAIなら人間は打てない
    if (!canPlayerMove()) {
        showStatus('現在あなたのターンではありません');
        return;
    }

    const row = parseInt(e.currentTarget.dataset.row, 10);
    const col = parseInt(e.currentTarget.dataset.col, 10);

    socket.emit('make_move', {
        game_id: currentGameId,
        row: row,
        col: col
    });
}

/**
 * ゲーム状態を更新
 */
function updateGameState(state) {
    currentGameState = state;

    // 変更があったセルを特定するため、前のボード状態と比較
    const changedCells = [];
    const newStoneCells = [];

    if (previousBoard) {
        for (let row = 0; row < 8; row++) {
            for (let col = 0; col < 8; col++) {
                const prevValue = previousBoard[row][col];
                const newValue = state.board[row][col];

                if (prevValue !== newValue) {
                    changedCells.push({ row, col, wasEmpty: prevValue === 0 });
                    // 前に何もなかった（0）から石が置かれた場合、これが最後の手番の位置
                    if (prevValue === 0 && newValue !== 0) {
                        newStoneCells.push({ row, col });
                    }
                }
            }
        }

        // 新しい石が置かれた位置をラストムーブとして記録
        if (newStoneCells.length > 0) {
            lastMovePosition = newStoneCells[newStoneCells.length - 1];
        }
    }

    // ボードの更新
    const gameBoard = document.getElementById('game-board');
    const cells = gameBoard.getElementsByClassName('cell');
    for (let i = 0; i < cells.length; i++) {
        const row = Math.floor(i / 8);
        const col = i % 8;
        const cell = cells[i];

        // 既存の石をクリア
        cell.innerHTML = '';
        cell.className = 'cell';

        // 有効な手をハイライト（人間のターンかつ石を置ける場合のみ）
        const isValidMove = state.valid_moves.some(move =>
            move[0] === row && move[1] === col);
        if (isValidMove && canPlayerMove()) {
            cell.classList.add('valid-move');
        }

        // ラストムーブのセルをハイライト
        if (lastMovePosition && row === lastMovePosition.row && col === lastMovePosition.col) {
            cell.classList.add('last-move');
        }

        // 石を配置
        if (state.board[row][col] === 1) { // 黒
            const stone = document.createElement('div');
            stone.className = 'stone black';

            // 新しく置かれた石にアニメーションを付与
            const isNewStone = newStoneCells.some(pos => pos.row === row && pos.col === col);
            if (isNewStone) {
                stone.classList.add('place-animation');
            }

            if (lastMovePosition && row === lastMovePosition.row && col === lastMovePosition.col) {
                stone.classList.add('last-placed');
            }

            cell.appendChild(stone);
        } else if (state.board[row][col] === 2) { // 白
            const stone = document.createElement('div');
            stone.className = 'stone white';

            // 新しく置かれた石にアニメーションを付与
            const isNewStone = newStoneCells.some(pos => pos.row === row && pos.col === col);
            if (isNewStone) {
                stone.classList.add('place-animation');
            }

            if (lastMovePosition && row === lastMovePosition.row && col === lastMovePosition.col) {
                stone.classList.add('last-placed');
            }

            cell.appendChild(stone);
        }
    }

    // 前のボード状態を保存（次の更新で比較するため）
    previousBoard = state.board.map(row => [...row]);

    // 情報パネルの更新
    updateScoreDisplay(state);

    // ゲーム状態の更新
    if (state.game_over) {
        setAIThinking(false);
        let message = 'ゲーム終了！';
        if (state.winner === 1) {
            message += ' 黒の勝利！';
        } else if (state.winner === 2) {
            message += ' 白の勝利！';
        } else {
            message += ' 引き分け！';
        }
        showStatus(message);
        gameActive = false;
        document.getElementById('start-btn').disabled = false;
        document.getElementById('reset-btn').disabled = false;
        document.getElementById('apply-ai-btn').disabled = false;
    } else {
        showStatus(`${state.current_player === 1 ? '黒' : '白'}のターン`);
        gameActive = true;
        document.getElementById('start-btn').disabled = true;
        document.getElementById('reset-btn').disabled = false;
        document.getElementById('apply-ai-btn').disabled = currentPlayMode !== 'ai';
    }

    // 有効な手がない場合
    if (state.valid_moves.length === 0 && !state.game_over) {
        showStatus('有効な手がありません。パスします。');
    }

    // AI ターンの判定と自動手選択
    if (!gameActive || state.game_over) {
        setAIThinking(false);
    } else {
        const currentIsBlack = state.current_player === 1;
        const currentTurnAI = currentIsBlack ? isBlackAI() : isWhiteAI();
        if (currentTurnAI) {
            const aiConfig = currentIsBlack ? currentAIInfo.black_ai : currentAIInfo.white_ai;
            setAIThinking(true, currentIsBlack ? 'black' : 'white', aiConfig?.algorithm || null);
            // AI の手選択を非同期で実行（UI をブロッキングしないため）
            setTimeout(() => handleAITurn(state), 100);
        } else {
            setAIThinking(false);
        }
    }

    // AI 状態の表示更新
    updateAIStatusDisplay();
}

/**
 * スコア表示を更新
 */
function updateScoreDisplay(state) {
    const blackCountEl = document.getElementById('black-count');
    const whiteCountEl = document.getElementById('white-count');
    const turnColorEl = document.getElementById('turn-color');
    const turnTextEl = document.getElementById('turn-text');

    blackCountEl.textContent = state.black_count;
    whiteCountEl.textContent = state.white_count;
    turnColorEl.style.backgroundColor =
        state.current_player === 1 ? '#000' : '#fff';
    turnColorEl.style.border =
        state.current_player === 2 ? '1px solid #ddd' : 'none';
    const currentTurnText = state.current_player === 1 ? '黒のターン' : '白のターン';
    if (typeof myAssignedRole === 'string' && myAssignedRole) {
        const yourTurn = (myAssignedRole === 'black' && state.current_player === 1)
            || (myAssignedRole === 'white' && state.current_player === 2);
        const whoText = yourTurn ? 'あなた' : (opponentName || '相手');
        turnTextEl.textContent = `${currentTurnText} (${whoText})`;
    } else {
        turnTextEl.textContent = currentTurnText;
    }
}

/**
 * イベントリスナーを設定
 */
function setupEventListeners() {
    const chooseSingleModeBtn = document.getElementById('choose-single-mode-btn');
    const chooseMultiModeBtn = document.getElementById('choose-multi-mode-btn');
    const startSingleBtn = document.getElementById('start-single-btn');
    const backFromSingleBtn = document.getElementById('back-from-single-btn');
    const singleSeatFirstBtn = document.getElementById('single-seat-first-btn');
    const singleSeatSecondBtn = document.getElementById('single-seat-second-btn');
    const startMatchBtn = document.getElementById('start-match-btn');
    const cancelMatchBtn = document.getElementById('cancel-match-btn');
    const chooseFirstBtn = document.getElementById('choose-first-btn');
    const chooseSecondBtn = document.getElementById('choose-second-btn');
    const startBtn = document.getElementById('start-btn');
    const resetBtn = document.getElementById('reset-btn');
    const modeManualBtn = document.getElementById('mode-manual-btn');
    const modeAIBtn = document.getElementById('mode-ai-btn');
    const blackAIEnable = document.getElementById('black-ai-enable');
    const whiteAIEnable = document.getElementById('white-ai-enable');
    const blackAlgorithmSelect = document.getElementById('black-algorithm');
    const whiteAlgorithmSelect = document.getElementById('white-algorithm');
    const applyAIBtn = document.getElementById('apply-ai-btn');

    chooseSingleModeBtn.addEventListener('click', () => {
        setGameMode('singleplayer');
    });

    chooseMultiModeBtn.addEventListener('click', () => {
        setGameMode('multiplayer');
    });

    startSingleBtn.addEventListener('click', () => {
        requestSingleplayerStart();
    });

    backFromSingleBtn.addEventListener('click', () => {
        setGameMode(null);
    });

    singleSeatFirstBtn.addEventListener('click', () => {
        selectSingleSeat('first');
    });

    singleSeatSecondBtn.addEventListener('click', () => {
        selectSingleSeat('second');
    });

    startMatchBtn.addEventListener('click', () => {
        requestMatchmakingStart();
    });

    cancelMatchBtn.addEventListener('click', () => {
        requestMatchmakingCancel();
    });

    chooseFirstBtn.addEventListener('click', () => {
        chooseRoleAfterMatch('first');
    });

    chooseSecondBtn.addEventListener('click', () => {
        chooseRoleAfterMatch('second');
    });

    startBtn.addEventListener('click', () => {
        if (!currentGameId) {
            showStatus('先にマッチングを完了してください');
            return;
        }
        setAIThinking(false);
        socket.emit('create_game', { game_id: currentGameId, game_type: 'othello' });
        socket.emit('get_ai_info', { game_id: currentGameId });
        startBtn.disabled = true;
        resetBtn.disabled = false;
        applyAIBtn.disabled = false;
        showStatus('新しいゲームを開始しました');
    });

    resetBtn.addEventListener('click', () => {
        if (!currentGameId) {
            showStatus('先にマッチングを完了してください');
            return;
        }
        setAIThinking(false);
        socket.emit('reset_game', { game_id: currentGameId, game_type: 'othello' });
        socket.emit('get_ai_info', { game_id: currentGameId });
        showStatus('ゲームをリセットしました');
    });

    modeManualBtn.addEventListener('click', () => {
        setPlayMode('manual');
    });

    modeAIBtn.addEventListener('click', () => {
        setPlayMode('ai');
    });

    blackAIEnable.addEventListener('change', updateAIToggleAvailability);
    whiteAIEnable.addEventListener('change', updateAIToggleAvailability);
    blackAlgorithmSelect.addEventListener('change', () => updateAIParameterVisibility('black'));
    whiteAlgorithmSelect.addEventListener('change', () => updateAIParameterVisibility('white'));

    applyAIBtn.addEventListener('click', () => {
        if (currentPlayMode !== 'ai') {
            showStatus('AI設定はAIプレイモードでのみ利用できます');
            return;
        }

        const blackDepthInput = document.getElementById('black-depth');
        const whiteDepthInput = document.getElementById('white-depth');
        const blackIterationsInput = document.getElementById('black-iterations');
        const whiteIterationsInput = document.getElementById('white-iterations');

        // 黒のAI設定
        const blackAlgorithm = blackAIEnable.checked ? blackAlgorithmSelect.value : 'none';
        socket.emit('set_ai', {
            game_id: currentGameId,
            color: 'black',
            difficulty: 'medium',
            algorithm: blackAlgorithm,
            depth: blackAlgorithm === 'minmax' ? parseInt(blackDepthInput.value, 10) : null,
            iterations: blackAlgorithm === 'mcts' ? parseInt(blackIterationsInput.value, 10) : null
        });

        // 白のAI設定
        const whiteAlgorithm = whiteAIEnable.checked ? whiteAlgorithmSelect.value : 'none';
        socket.emit('set_ai', {
            game_id: currentGameId,
            color: 'white',
            difficulty: 'medium',
            algorithm: whiteAlgorithm,
            depth: whiteAlgorithm === 'minmax' ? parseInt(whiteDepthInput.value, 10) : null,
            iterations: whiteAlgorithm === 'mcts' ? parseInt(whiteIterationsInput.value, 10) : null
        });

        showStatus('AI設定を適用しました');
    });
}

/**
 * ページロード時の初期化
 */
function initializeUI() {
    setupEventListeners();
    selectSingleSeat('first');
    setGameMode(null, { persist: false });
    if (typeof toggleGamePanels === 'function') {
        toggleGamePanels(false);
    }
    initializeGame();
}

// Dom Content Loaded で初期化
document.addEventListener('DOMContentLoaded', initializeUI);
