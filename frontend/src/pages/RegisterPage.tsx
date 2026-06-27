import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserPlus, ArrowLeft, CheckCircle } from 'lucide-react';
import { authApi } from '../api/apiService';
import styles from './RegisterPage.module.css';

interface FieldErrors {
  username?: string;
  email?: string;
  password?: string;
  rePassword?: string;
  fullName?: string;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rePassword, setRePassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const validate = (): boolean => {
    const errors: FieldErrors = {};

    if (!username) {
      errors.username = 'Введите логин';
    } else if (username.startsWith(' ')) {
      errors.username = 'Логин не может начинаться с пробела';
    } else if (/^\d+$/.test(username)) {
      errors.username = 'Логин не может состоять только из цифр';
    } else if (username.length < 4) {
      errors.username = 'Минимум 4 символа';
    }

    if (email && email.startsWith(' ')) {
      errors.email = 'Email не может начинаться с пробела';
    } else if (email && !EMAIL_REGEX.test(email)) {
      errors.email = 'Некорректный формат email';
    }

    if (!fullName) {
      errors.fullName = 'Введите ФИО';
    } else if (fullName.length < 2) {
      errors.fullName = 'ФИО должно содержать минимум 2 символа';
    }

    if (!password) {
      errors.password = 'Введите пароль';
    } else if (password.startsWith(' ')) {
      errors.password = 'Пароль не может начинаться с пробела';
    } else if (/^\d+$/.test(password)) {
      errors.password = 'Пароль не может состоять только из цифр';
    } else if (password.length < 8) {
      errors.password = 'Минимум 8 символов';
    }

    if (!rePassword) {
      errors.rePassword = 'Повторите пароль';
    } else if (password && password !== rePassword) {
      errors.rePassword = 'Пароли не совпадают';
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);

    if (!validate()) return;

    setIsLoading(true);
    try {
      await authApi.register({
        username,
        password,
        re_password: rePassword,
        email: email || undefined,
        full_name: fullName,
      });
      setIsSuccess(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string') {
        setGeneralError(detail);
      } else if (Array.isArray(detail)) {
        // Pydantic validation errors — map to fields
        const errors: FieldErrors = {};
        for (const e of detail) {
          const field = e.loc?.[e.loc.length - 1];
          const msg = e.msg || e.message || '';
          if (field === 'email') {
            errors.email = 'Некорректный формат email';
          } else if (field === 'username') {
            errors.username = msg;
          } else if (field === 'password') {
            errors.password = msg;
          } else if (field === 're_password') {
            errors.rePassword = msg;
          }
        }
        if (Object.keys(errors).length > 0) {
          setFieldErrors(errors);
        } else {
          setGeneralError('Ошибка валидации данных');
        }
      } else {
        setGeneralError('Ошибка регистрации');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Clear field error on change
  const handleChange = (field: keyof FieldErrors, value: string, setter: (v: string) => void) => {
    setter(value);
    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  return (
    <div className={styles.page}>
      {/* Left: orange panel */}
      <div className={styles.left}>
        <div className={styles.leftPattern} />
        <div className={styles.leftDividerH} />
        <div className={styles.leftDividerV} />
        <div className={styles.leftContent}>
          <UserPlus size={120} strokeWidth={1} className={styles.leftIcon} />
          <p className={styles.leftLabel}>New_User</p>
        </div>
      </div>

      {/* Right: form or success */}
      <div className={styles.right}>
        <button className={styles.backBtn} onClick={() => navigate('/login')} type="button">
          <ArrowLeft size={24} />
        </button>

        {isSuccess ? (
          <div className={styles.successContainer}>
            <CheckCircle size={72} strokeWidth={1.5} className={styles.successIcon} />
            <h1 className={styles.successTitle}>Регистрация</h1>
            <p className={styles.successText}>
              Аккаунт успешно создан.<br />
              Ожидайте подтверждения администратором.
            </p>
            <button
              className={styles.successBtn}
              onClick={() => navigate('/login')}
              type="button"
            >
              Вернуться ко входу
            </button>
          </div>
        ) : (
          <form className={styles.form} onSubmit={handleSubmit} noValidate>
            <h1 className={styles.title}>Регистрация</h1>

            <div className={styles.fields}>
              <div className={styles.fieldGroup}>
                <input
                  type="text"
                  className={`${styles.input} ${fieldErrors.username ? styles.inputError : ''}`}
                  placeholder="Логин"
                  value={username}
                  onChange={(e) => handleChange('username', e.target.value, setUsername)}
                  disabled={isLoading}
                  autoComplete="username"
                />
                {fieldErrors.username && (
                  <span className={styles.fieldError}>{fieldErrors.username}</span>
                )}
              </div>

              <div className={styles.fieldGroup}>
                <input
                  type="email"
                  className={`${styles.input} ${fieldErrors.email ? styles.inputError : ''}`}
                  placeholder="Email (необязательно)"
                  value={email}
                  onChange={(e) => handleChange('email', e.target.value, setEmail)}
                  disabled={isLoading}
                  autoComplete="email"
                />
                {fieldErrors.email && (
                  <span className={styles.fieldError}>{fieldErrors.email}</span>
                )}
              </div>

              <div className={styles.fieldGroup}>
                <input
                  type="text"
                  className={`${styles.input} ${fieldErrors.fullName ? styles.inputError : ''}`}
                  placeholder="ФИО"
                  value={fullName}
                  onChange={(e) => handleChange('fullName', e.target.value, setFullName)}
                  disabled={isLoading}
                  autoComplete="name"
                />
                {fieldErrors.fullName && (
                  <span className={styles.fieldError}>{fieldErrors.fullName}</span>
                )}
              </div>

              <div className={styles.fieldGroup}>
                <input
                  type="password"
                  className={`${styles.input} ${fieldErrors.password ? styles.inputError : ''}`}
                  placeholder="Пароль"
                  value={password}
                  onChange={(e) => handleChange('password', e.target.value, setPassword)}
                  disabled={isLoading}
                  autoComplete="new-password"
                />
                {fieldErrors.password && (
                  <span className={styles.fieldError}>{fieldErrors.password}</span>
                )}
              </div>

              <div className={styles.fieldGroup}>
                <input
                  type="password"
                  className={`${styles.input} ${fieldErrors.rePassword ? styles.inputError : ''}`}
                  placeholder="Пароль повторно"
                  value={rePassword}
                  onChange={(e) => handleChange('rePassword', e.target.value, setRePassword)}
                  disabled={isLoading}
                  autoComplete="new-password"
                />
                {fieldErrors.rePassword && (
                  <span className={styles.fieldError}>{fieldErrors.rePassword}</span>
                )}
              </div>
            </div>

            {generalError && <p className={styles.error}>{generalError}</p>}

            <button type="submit" className={styles.submitBtn} disabled={isLoading}>
              {isLoading ? 'Загрузка...' : 'Зарегистрироваться'}
            </button>

            <div className={styles.links}>
              <button
                type="button"
                className={styles.link}
                onClick={() => navigate('/login')}
              >
                Уже есть аккаунт? Войти
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default RegisterPage;
