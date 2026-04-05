(function () {
    const PIECE_SCORE = {
        0: 0,
        1: 1,
        2: 3,
        3: 3,
        4: 5,
        5: 6,
        6: 8,
        7: 9,
        8: 100,
        9: 5,
        10: 5,
        11: 5,
        12: 6,
        13: 10,
        14: 11,
    };

    function isOpponentPiece(player, piece) {
        if (piece === 0) {
            return false;
        }
        if (player === 1) {
            return piece < 0;
        }
        return piece > 0;
    }

    function captureScore(state, move) {
        const to = move && move.to;
        if (!Array.isArray(to) || to.length !== 2) {
            return 0;
        }
        const row = to[0];
        const col = to[1];
        const board = state && state.board;
        if (!Array.isArray(board) || !Array.isArray(board[row])) {
            return 0;
        }
        const piece = board[row][col] || 0;
        if (!isOpponentPiece(state.current_player, piece)) {
            return 0;
        }
        return (PIECE_SCORE[Math.abs(piece)] || 0) * 12;
    }

    function dropScore(move) {
        if (!move || !move.drop_piece) {
            return 0;
        }
        // Favor active piece drops slightly over passive shuffle moves.
        return 4;
    }

    function promotionScore(move) {
        return move && move.promote ? 7 : 0;
    }

    function centerScore(move) {
        const to = move && move.to;
        if (!Array.isArray(to) || to.length !== 2) {
            return 0;
        }
        const row = to[0];
        const col = to[1];
        const dr = Math.abs(4 - row);
        const dc = Math.abs(4 - col);
        return Math.max(0, 4 - dr - dc);
    }

    function forwardScore(state, move) {
        if (!move || !Array.isArray(move.to) || move.to.length !== 2) {
            return 0;
        }
        if (!Array.isArray(move.from) || move.from.length !== 2) {
            return 0;
        }

        const fromRow = move.from[0];
        const toRow = move.to[0];
        const delta = toRow - fromRow;

        if (state.current_player === 1) {
            return delta < 0 ? 3 : 0;
        }
        return delta > 0 ? 3 : 0;
    }

    function mobilityNoise() {
        return Math.random() * 2;
    }

    function evaluateMove(state, move, config) {
        let score = 0;
        score += captureScore(state, move);
        score += promotionScore(move);
        score += dropScore(move);
        score += centerScore(move);
        score += forwardScore(state, move);

        const difficulty = (config && config.difficulty) || "medium";
        if (difficulty === "easy") {
            score += Math.random() * 16;
        } else if (difficulty === "hard") {
            score += mobilityNoise();
        } else {
            score += Math.random() * 4;
        }
        return score;
    }

    function chooseWeightedBest(scoredMoves, keepTopN) {
        if (!Array.isArray(scoredMoves) || scoredMoves.length === 0) {
            return null;
        }
        const sorted = [...scoredMoves].sort((a, b) => b.score - a.score);
        const candidates = sorted.slice(0, Math.max(1, keepTopN));
        const pick = candidates[Math.floor(Math.random() * candidates.length)];
        return pick.move;
    }

    function selectMove(gameState, aiConfig) {
        const validMoves = gameState && Array.isArray(gameState.valid_moves)
            ? gameState.valid_moves
            : [];
        if (validMoves.length === 0) {
            return null;
        }

        const scored = validMoves.map((move) => ({
            move,
            score: evaluateMove(gameState, move, aiConfig),
        }));

        const difficulty = (aiConfig && aiConfig.difficulty) || "medium";
        if (difficulty === "easy") {
            return chooseWeightedBest(scored, 5);
        }
        if (difficulty === "hard") {
            return chooseWeightedBest(scored, 1);
        }
        return chooseWeightedBest(scored, 3);
    }

    window.ShogiBrowserAI = {
        selectMove,
    };
})();
