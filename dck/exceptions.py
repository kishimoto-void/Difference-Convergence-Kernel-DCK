"""DCK 専用例外階層"""

class DCKError(Exception):
    """DCKにおける基底例外"""
    pass

class ResourceExhaustedError(DCKError):
    """DCK リソース不足時の例外"""
    pass

class TransactionExecutionError(DCKError):
    """DCK トランザクション実行失敗時の例外"""
    pass

class SnapshotError(DCKError):
    """DCK スナップショット生成不整合時の例外"""
    pass
