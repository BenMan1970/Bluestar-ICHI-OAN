# ... (tous vos imports et fonctions restent les mêmes)

# --- Interface Streamlit ---
st.title("Scanner de Marché Ichimoku")
st.write("Analyse les croisements Tenkan/Kijun avec filtres sur H1 et H4.")

# Test sur un instrument pour commencer
instrument_test = "EUR_USD"
timeframe_test = "H1"

st.header(f"Analyse test pour {instrument_test} sur {timeframe_test}")

if st.button("Lancer le test"):
    # Étape 1: Récupérer les données
    df_candles = fetch_candles(instrument_test, timeframe_test, 150)

    if df_candles is not None:
        # Étape 2: Calculer Ichimoku
        df_with_indicators = add_ichimoku(df_candles)
        
        st.success("Données récupérées et indicateurs calculés !")
        st.dataframe(df_with_indicators.tail(5)) # On affiche juste les 5 dernières pour vérifier

        # --- ÉTAPE 3: DÉTECTION DU CROISEMENT ---

        # 3.A - Renommer les colonnes pour la lisibilité
        df_with_indicators.rename(columns={
            "ITS_9": "tenkan",
            "IKS_26": "kijun",
            "ISA_26": "senkou_a",
            "ISB_52": "senkou_b",
            "ICS_26": "chikou"
        }, inplace=True)

        # 3.B - Isoler les deux dernières bougies
        last_two_candles = df_with_indicators.iloc[-2:]
        
        if len(last_two_candles) < 2:
            st.warning("Pas assez de données pour détecter un croisement.")
        else:
            previous_candle = last_two_candles.iloc[0]
            last_candle = last_two_candles.iloc[1]

            # 3.C - Logique de détection du croisement
            st.subheader("Résultat de l'analyse du croisement :")

            # Condition pour un croisement haussier
            if last_candle['tenkan'] > last_candle['kijun'] and previous_candle['tenkan'] <= previous_candle['kijun']:
                st.success(f"✅ Signal de croisement HAUSSIER détecté sur {instrument_test} !")
                st.write(f"Heure du signal (UTC) : {last_candle.name}")

            # Condition pour un croisement baissier
            elif last_candle['tenkan'] < last_candle['kijun'] and previous_candle['tenkan'] >= previous_candle['kijun']:
                st.error(f"❌ Signal de croisement BAISSIER détecté sur {instrument_test} !")
                st.write(f"Heure du signal (UTC) : {last_candle.name}")

            else:
                st.info("Aucun croisement Tenkan/Kijun détecté sur la dernière bougie.")
       
