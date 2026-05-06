# 多账号系统使用说明（Multi-Account Guide）

## 📦 功能概述

当前框架已支持**多账号任务执行机制**，可以实现：

* 多账号顺序执行任务
* 每个账号独立配置（参数隔离）
* 与以下功能联动：

  * 计划任务（ScheduleTaskTab）
  * 账号配置界面（AccountConfigTab）

---

## 🚀 快速开始

### 1️⃣ 在任务中开启多账号支持

```python
class MyTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.support_multi_account = True
        self.support_schedule_task = True  # 可选

    def run(self):
        if self.multi_account_mode:
            self.run_multi_account()
        else:
            self.run_one_account({
                "username": "default",
                "password": "",
                "account_id": ""
            })
```

---

## 🔴 必须实现的接口（不实现会直接报错）

开启：

```python
self.support_multi_account = True
```

必须实现以下方法：

---

### 1. 登录逻辑(判定为未登录时执行的登录函数)

```python
def do_login(self, username: str, password: str = "") -> bool:
    """
    执行登录逻辑

    返回：
        True  -> 登录成功
        False -> 登录失败
    """
    raise NotImplementedError
```

### 2. 单账号任务执行

```python
def run_one_account(self, account: dict):
    """
    执行单账号任务

    account = {
        "username": str,
        "password": str（可能为空）, 
        "account_id": str
    }
    """
    raise NotImplementedError
```

---

## 🟡 可选钩子（不写也能跑）

```python
def do_logout(self):
    """每个账号执行完成后调用"""
    pass

def on_account_switch(self, old, new):
    """切换账号前调用"""
    pass

def is_logged_in(self, username: str) -> bool:
    """
    判断当前是否已登录该账号
    默认返回 False（可选覆写）
    """
    return False
```

---

## 📄 账号列表格式

配置方式（UI 或配置项）：

```
账号1
账号2,密码2
账号3
```

---

### ✅ 规则说明

* 每行一个账号
* 支持两种格式：

  * `username`
  * `username,password`
* 密码是**可选的**

---

### ✅ 解析结果

```python
[
  {"username": "账号1", "password": ""},
  {"username": "账号2", "password": "密码2"}
]
```

---

## ⚙️ 执行流程（核心逻辑）

调用：

```python
self.run_multi_account()
```

内部逻辑：

```
for account in account_list:
    if not is_logged_in():
        do_login()

    应用账号配置覆盖

    执行 run_one_account()

    执行 do_logout()
```

---

## 🧩 自动注入配置项

当开启：

```python
self.support_multi_account = True
```

系统会自动增加：

* Multi Account Mode（多账号模式开关）
* Multi Account Independent Config（账号独立配置）
* Account List（账号列表）

---

## 🖥 UI 功能说明

---

### ✅ AccountConfigTab（账号配置界面）

自动出现条件：

```python
任意任务 support_multi_account = True
```

功能：

* 编辑账号列表
* 选择账号 + 任务
* 修改该账号的独立配置
* 保存 / 清除配置

---

### ✅ ScheduleTaskTab（计划任务支持）

支持账号参数：

```
-a 账号名
```

示例：

```
python main.py -a account1
```


## 🧠 进阶说明


### 账号 ID（account_id）

系统会为每个账号生成稳定 ID：

```
username → account_id
```

用途：

* 配置隔离
* 持久化存储

---

### 密码处理

* 可为空
* 不提供时为 `""`
* 任务代码必须兼容

---

## 🎯 总结

启用多账号只需要 4 步：

1. 设置：

   ```python
   self.support_multi_account = True
   ```

2. 实现 2 个核心接口（`do_login`、`run_one_account`），`is_logged_in` 可选

3. 在 run() 中调用：

   ```python
   self.run_multi_account()
   ```

4. 在 UI 配置账号列表

---

## 💬 最小示例

```python
class DemoTask(BaseTask):
    def __init__(self):
        super().__init__()
        self.support_multi_account = True

    def is_logged_in(self, username):
        return False

    def do_login(self, username, password=""):
        print(f"登录: {username}")
        return True

    def run_one_account(self, account):
        print(f"执行任务: {account['username']}")
```

---
