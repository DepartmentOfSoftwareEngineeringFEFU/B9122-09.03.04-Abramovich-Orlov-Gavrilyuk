import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, ArrowLeft, MailCheck } from 'lucide-react';
import { authApi } from '../api/apiService';
import styles from './ForgotPasswordPage.module.css';

export const ForgotPasswordPage: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setError('Введите email');
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await authApi.forgotPassword(email);
      setIsSuccess(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Ошибка при запросе');
    } finally {
      setIsLoading(false);
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
          <KeyRound size={120} strokeWidth={1} className={styles.leftIcon} />
          <p className={styles.leftLabel}>Password_Reset</p>
        </div>
      </div>

      {/* Right: form or success */}
      <div className={styles.right}>
        <button className={styles.backBtn} onClick={() => navigate('/login')} type="button">
          <ArrowLeft size={24} />
        </button>

        {isSuccess ? (
          <div className={styles.successContainer}>
            <MailCheck size={72} strokeWidth={1.5} className={styles.successIcon} />
            <h1 className={styles.successTitle}>Сброс пароля</h1>
            <p className={styles.successText}>
              Если аккаунт с указанным email существует,<br />
              инструкции по сбросу пароля отправлены<br />
              на вашу почту.
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
            <h1 className={styles.title}>Сброс пароля</h1>
            <p className={styles.subtitle}>
              Для восстановления пароля введите email,<br />
              указанный при регистрации
            </p>

            <div className={styles.fields}>
              <input
                type="email"
                className={`${styles.input} ${error ? styles.inputError : ''}`}
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                autoComplete="email"
              />
            </div>

            {error && <p className={styles.error}>{error}</p>}

            <button type="submit" className={styles.submitBtn} disabled={isLoading}>
              {isLoading ? 'Загрузка...' : 'Отправить'}
            </button>

            <div className={styles.links}>
              <button
                type="button"
                className={styles.link}
                onClick={() => navigate('/register')}
              >
                Зарегистрироваться
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
