from __future__ import annotations

import argparse
import os

import numpy as np
import onnx
from onnx import TensorProto, helper


def build_linear_policy_model(
    feature_dim: int, weights: np.ndarray, bias: float
) -> onnx.ModelProto:
    x = helper.make_tensor_value_info(
        "features", TensorProto.FLOAT, [None, feature_dim]
    )
    y = helper.make_tensor_value_info("scores", TensorProto.FLOAT, [None, 1])

    w_tensor = helper.make_tensor(
        name="W",
        data_type=TensorProto.FLOAT,
        dims=[feature_dim, 1],
        vals=weights.astype(np.float32).reshape(feature_dim, 1).flatten().tolist(),
    )
    b_tensor = helper.make_tensor(
        name="B",
        data_type=TensorProto.FLOAT,
        dims=[1],
        vals=[np.float32(bias).item()],
    )

    matmul_node = helper.make_node(
        "MatMul", inputs=["features", "W"], outputs=["matmul_out"]
    )
    add_node = helper.make_node("Add", inputs=["matmul_out", "B"], outputs=["scores"])

    graph = helper.make_graph(
        nodes=[matmul_node, add_node],
        name="ShogiPolicyLinear",
        inputs=[x],
        outputs=[y],
        initializer=[w_tensor, b_tensor],
    )

    model = helper.make_model(
        graph,
        producer_name="othello-game-shogi-policy",
        opset_imports=[helper.make_operatorsetid("", 13)],
    )
    onnx.checker.check_model(model)
    return model


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export shogi linear policy weights to ONNX"
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=os.path.join("backend", "models", "shogi_policy_weights.npz"),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join("backend", "models", "shogi_policy.onnx"),
    )
    args = parser.parse_args()

    data = np.load(args.weights)
    weights = data["weights"].astype(np.float32)
    bias = float(data["bias"].astype(np.float32).item())
    feature_dim = int(data["feature_dim"].item())

    model = build_linear_policy_model(feature_dim, weights, bias)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    onnx.save(model, args.output)
    print(f"saved onnx model: {args.output}")


if __name__ == "__main__":
    main()
