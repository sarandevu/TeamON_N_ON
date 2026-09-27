# Contributing to EdgePPG

Thank you for your interest in contributing to **EdgePPG**! This document provides guidelines and workflows for submitting issues, proposing architectural improvements, and creating pull requests.

---

## 🛠️ Development Setup

### Python Environment
1. Clone the repository:
   ```bash
   git clone https://github.com/sarandevu/TeamON_N_ON.git
   cd TeamON_N_ON
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install cryptography pytest ruff black
   ```

### Android Environment
1. Open the `android/` directory in Android Studio (Giraffe/Hedgehog/Iguana or newer).
2. Ensure JDK 17+ and Android SDK API 34+ are configured.
3. Build the project:
   ```bash
   cd android
   ./gradlew assembleDebug
   ```

---

## 🧪 Testing Guidelines

Before submitting a Pull Request, all tests must pass:

1. **Python Verifier Suite**:
   ```bash
   python -m unittest discover verifier/tests
   ```
2. **ML Pipeline & Parity Tests**:
   ```bash
   python -m tests.run_all_tests
   ```
3. **Android Unit Tests**:
   ```bash
   cd android
   ./gradlew testDebugUnitTest
   ```

---

## 📐 Code Style & Conventions

- **Kotlin**: Follow official [Kotlin Coding Conventions](https://kotlinlang.org/docs/coding-conventions.html).
- **Python**: PEP 8 compliance; maximum line length 100 characters (`ruff` and `black`).
- **Claim Discipline**: Do NOT claim the system is "100% unspoofable" or "deepfake-proof". State all biometric and cryptographic guarantees objectively with empirical metrics and thresholds.
- **Commit Messages**: Use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).

---

## 🔒 Security Vulnerabilities

Please do NOT file public GitHub issues for sensitive security bugs or potential cryptographic bypasses. Refer to [SECURITY.md](SECURITY.md) for reporting instructions.
