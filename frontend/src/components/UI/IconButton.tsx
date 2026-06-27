import React from 'react';
import styles from './IconButton.module.css';

interface IconButtonProps {
  icon: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  title?: string;
}

export const IconButton: React.FC<IconButtonProps> = ({
  icon,
  active = false,
  onClick,
  title,
}) => {
  const classes = [styles.iconBtn, active ? styles.active : styles.inactive].filter(Boolean).join(' ');

  return (
    <button type="button" className={classes} onClick={onClick} title={title}>
      {icon}
    </button>
  );
};
