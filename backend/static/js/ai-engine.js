/**
 * AI エンジン（ブラウザ版）
 * MinMax と MCTS 探索をJavaScriptで実装
 */

const PLAYER = {
    BLACK: 1,
    WHITE: 2,
    EMPTY: 0
};

class GameStateJS {
    constructor(boardData = null) {
        if (boardData) {
            this.board = boardData.board.map(row => [...row]);
            this.current_player = boardData.current_player;
            this.game_over = boardData.game_over;
            this.winner = boardData.winner;
        } else {
            this.board = Array(8).fill(null).map(() => Array(8).fill(PLAYER.EMPTY));
            this.board[3][3] = PLAYER.WHITE;
            this.board[3][4] = PLAYER.BLACK;
            this.board[4][3] = PLAYER.BLACK;
            this.board[4][4] = PLAYER.WHITE;
            this.current_player = PLAYER.BLACK;
            this.game_over = false;
            this.winner = null;
        }
    }

    getValidMoves() {
        const validMoves = [];
        const opponent = this.current_player === PLAYER.BLACK ? PLAYER.WHITE : PLAYER.BLACK;

        for (let row = 0; row < 8; row++) {
            for (let col = 0; col < 8; col++) {
                if (this.board[row][col] === PLAYER.EMPTY) {
                    if (this._isValidMove(row, col, opponent)) {
                        validMoves.push([row, col]);
                    }
                }
            }
        }
        return validMoves;
    }

    _isValidMove(row, col, opponent) {
        const directions = [
            [-1, -1], [-1, 0], [-1, 1],
            [0, -1], [0, 1],
            [1, -1], [1, 0], [1, 1]
        ];

        for (const [dx, dy] of directions) {
            if (this._checkDirection(row, col, dx, dy, opponent)) {
                return true;
            }
        }
        return false;
    }

    _checkDirection(row, col, dx, dy, opponent) {
        let x = row + dx, y = col + dy;
        let foundOpponent = false;

        while (x >= 0 && x < 8 && y >= 0 && y < 8) {
            if (this.board[x][y] === opponent) {
                foundOpponent = true;
            } else if (this.board[x][y] === this.current_player) {
                return foundOpponent;
            } else {
                break;
            }
            x += dx;
            y += dy;
        }
        return false;
    }

    makeMove(row, col) {
        if (!this._isValidMove(row, col,
            this.current_player === PLAYER.BLACK ? PLAYER.WHITE : PLAYER.BLACK)) {
            return false;
        }

        this.board[row][col] = this.current_player;
        this._flipStones(row, col);
        this._updateGameState();
        return true;
    }

    _flipStones(row, col) {
        const opponent = this.current_player === PLAYER.BLACK ? PLAYER.WHITE : PLAYER.BLACK;
        const directions = [
            [-1, -1], [-1, 0], [-1, 1],
            [0, -1], [0, 1],
            [1, -1], [1, 0], [1, 1]
        ];

        for (const [dx, dy] of directions) {
            const toFlip = this._getFlippableStones(row, col, dx, dy, opponent);
            for (const [fx, fy] of toFlip) {
                this.board[fx][fy] = this.current_player;
            }
        }
    }

    _getFlippableStones(row, col, dx, dy, opponent) {
        const toFlip = [];
        let x = row + dx, y = col + dy;

        while (x >= 0 && x < 8 && y >= 0 && y < 8) {
            if (this.board[x][y] === opponent) {
                toFlip.push([x, y]);
            } else if (this.board[x][y] === this.current_player) {
                return toFlip.length > 0 ? toFlip : [];
            } else {
                return [];
            }
            x += dx;
            y += dy;
        }
        return [];
    }

    _updateGameState() {
        this.current_player = this.current_player === PLAYER.BLACK ? PLAYER.WHITE : PLAYER.BLACK;

        let hasValidMoves = this.getValidMoves().length > 0;
        if (!hasValidMoves) {
            this.current_player = this.current_player === PLAYER.BLACK ? PLAYER.WHITE : PLAYER.BLACK;
            hasValidMoves = this.getValidMoves().length > 0;

            if (!hasValidMoves) {
                this.game_over = true;
                const blackCount = this.board.flat().filter(p => p === PLAYER.BLACK).length;
                const whiteCount = this.board.flat().filter(p => p === PLAYER.WHITE).length;
                if (blackCount > whiteCount) {
                    this.winner = PLAYER.BLACK;
                } else if (blackCount < whiteCount) {
                    this.winner = PLAYER.WHITE;
                } else {
                    this.winner = 0;
                }
            }
        }
    }

    copy() {
        return new GameStateJS(this);
    }

    evaluateBoard() {
        if (this.game_over) {
            const blackCount = this.board.flat().filter(p => p === PLAYER.BLACK).length;
            const whiteCount = this.board.flat().filter(p => p === PLAYER.WHITE).length;
            const diff = blackCount - whiteCount;
            return diff * 100;
        }

        let score = 0;

        const positionWeights = [
            [100, -10, 10, 5, 5, 10, -10, 100],
            [-10, -50, -5, -5, -5, -5, -50, -10],
            [10, -5, 5, 1, 1, 5, -5, 10],
            [5, -5, 1, 1, 1, 1, -5, 5],
            [5, -5, 1, 1, 1, 1, -5, 5],
            [10, -5, 5, 1, 1, 5, -5, 10],
            [-10, -50, -5, -5, -5, -5, -50, -10],
            [100, -10, 10, 5, 5, 10, -10, 100],
        ];

        for (let row = 0; row < 8; row++) {
            for (let col = 0; col < 8; col++) {
                if (this.board[row][col] === PLAYER.BLACK) {
                    score += positionWeights[row][col];
                } else if (this.board[row][col] === PLAYER.WHITE) {
                    score -= positionWeights[row][col];
                }
            }
        }

        const mobility = this.getValidMoves().length;
        const originalPlayer = this.current_player;
        this.current_player = this.current_player === PLAYER.BLACK ? PLAYER.WHITE : PLAYER.BLACK;
        const opponentMobility = this.getValidMoves().length;
        this.current_player = originalPlayer;

        score += (mobility - opponentMobility) * 10;

        return score;
    }
}

class MinMaxAI {
    constructor(difficulty = 'medium', depth = null) {
        this.difficulty = difficulty;
        this.depthMap = { 'easy': 2, 'medium': 3, 'hard': 4 };
        this.depth = depth || this.depthMap[difficulty] || 3;
    }

    getMove(gameState, shouldStop = null) {
        const validMoves = gameState.getValidMoves();
        if (validMoves.length === 0) return null;

        if (shouldStop && shouldStop()) return null;

        const isMaximizing = gameState.current_player === PLAYER.BLACK;
        let bestScore = isMaximizing ? -Infinity : Infinity;
        let bestMove = validMoves[0];

        for (const move of validMoves) {
            if (shouldStop && shouldStop()) return null;

            const newState = gameState.copy();
            newState.makeMove(move[0], move[1]);
            const score = this._minmax(newState, this.depth - 1, -Infinity, Infinity, !isMaximizing, shouldStop);

            if (score === null) return null;

            if (isMaximizing ? score > bestScore : score < bestScore) {
                bestScore = score;
                bestMove = move;
            }
        }
        return bestMove;
    }

    _minmax(gameState, depth, alpha, beta, isMaximizing, shouldStop = null) {
        if (shouldStop && shouldStop()) {
            return null;
        }

        if (depth === 0 || gameState.game_over) {
            return gameState.evaluateBoard();
        }

        const validMoves = gameState.getValidMoves();
        if (validMoves.length === 0) {
            const newState = gameState.copy();
            newState._updateGameState();
            return this._minmax(newState, depth - 1, alpha, beta, !isMaximizing, shouldStop);
        }

        if (isMaximizing) {
            let maxEval = -Infinity;
            for (const move of validMoves) {
                if (shouldStop && shouldStop()) return null;

                const newState = gameState.copy();
                newState.makeMove(move[0], move[1]);
                const evalScore = this._minmax(newState, depth - 1, alpha, beta, false, shouldStop);
                if (evalScore === null) return null;
                maxEval = Math.max(maxEval, evalScore);
                alpha = Math.max(alpha, evalScore);
                if (beta <= alpha) break;
            }
            return maxEval;
        } else {
            let minEval = Infinity;
            for (const move of validMoves) {
                if (shouldStop && shouldStop()) return null;

                const newState = gameState.copy();
                newState.makeMove(move[0], move[1]);
                const evalScore = this._minmax(newState, depth - 1, alpha, beta, true, shouldStop);
                if (evalScore === null) return null;
                minEval = Math.min(minEval, evalScore);
                beta = Math.min(beta, evalScore);
                if (beta <= alpha) break;
            }
            return minEval;
        }
    }
}

class MCTSAI {
    constructor(difficulty = 'medium', iterations = null) {
        this.difficulty = difficulty;
        this.iterationMap = { 'easy': 50, 'medium': 100, 'hard': 200 };
        this.iterations = iterations || this.iterationMap[difficulty] || 100;
    }

    getMove(gameState, shouldStop = null) {
        const validMoves = gameState.getValidMoves();
        if (validMoves.length === 0) return null;

        if (shouldStop && shouldStop()) return null;

        const root = new MCTSNode(null, gameState.copy(), null);

        for (let i = 0; i < this.iterations; i++) {
            if (shouldStop && shouldStop()) return null;

            const node = this._selectNode(root);
            if (!node.gameState.game_over && node.visits > 0) {
                this._expandNode(node);
            }

            const result = this._simulate(node.gameState.copy(), shouldStop);
            if (result === null) return null;
            this._backpropagate(node, result);
        }

        if (root.children.length === 0) {
            return validMoves[Math.floor(Math.random() * validMoves.length)];
        }

        const bestChild = root.children.reduce((best, child) =>
            child.visits > best.visits ? child : best
        );

        return bestChild.move;
    }

    _selectNode(node) {
        while (node.children.length > 0) {
            node = node.children.reduce((best, child) =>
                child.ucb1() > best.ucb1() ? child : best
            );
        }
        return node;
    }

    _expandNode(node) {
        const validMoves = node.gameState.getValidMoves();
        if (validMoves.length === 0) return;

        const triedMoves = new Set(node.children.map(c => JSON.stringify(c.move)));
        const untriedMoves = validMoves.filter(m => !triedMoves.has(JSON.stringify(m)));

        if (untriedMoves.length > 0) {
            const move = untriedMoves[Math.floor(Math.random() * untriedMoves.length)];
            const newState = node.gameState.copy();
            newState.makeMove(move[0], move[1]);
            const childNode = new MCTSNode(node, newState, move);
            node.children.push(childNode);
        }
    }

    _simulate(gameState, shouldStop = null) {
        let maxTurns = 64;
        let turnCount = 0;

        while (!gameState.game_over && turnCount < maxTurns) {
            if (shouldStop && shouldStop()) {
                return null;
            }

            const validMoves = gameState.getValidMoves();
            if (validMoves.length === 0) {
                gameState._updateGameState();
                turnCount++;
                continue;
            }

            const move = validMoves[Math.floor(Math.random() * validMoves.length)];
            gameState.makeMove(move[0], move[1]);
            turnCount++;
        }

        if (gameState.winner === PLAYER.BLACK) {
            return 1.0;
        } else if (gameState.winner === PLAYER.WHITE) {
            return -1.0;
        } else {
            return 0.0;
        }
    }

    _backpropagate(node, result) {
        while (node !== null) {
            node.visits++;
            node.value += result;
            result = -result;
            node = node.parent;
        }
    }
}

class MCTSNode {
    constructor(parent, gameState, move) {
        this.parent = parent;
        this.gameState = gameState;
        this.move = move;
        this.children = [];
        this.visits = 0;
        this.value = 0.0;
    }

    ucb1() {
        if (this.visits === 0) return Infinity;
        if (this.parent === null) return 0;

        const explorationWeight = Math.sqrt(2);
        return (this.value / this.visits) +
            explorationWeight * Math.sqrt(Math.log(this.parent.visits) / this.visits);
    }
}
