using System.Collections;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

public class ButtonBlink : MonoBehaviour, ISelectHandler, IDeselectHandler
{
    private Image image;
    private Coroutine blinkCoroutine;
    public Color originalColor;

    void Awake()
    {
        image = GetComponent<Image>();
        originalColor = image.color;
    }

    public void OnSelect(BaseEventData eventData)
    {
        blinkCoroutine = StartCoroutine(Blink());
    }

    public void OnDeselect(BaseEventData eventData)
    {
        if (blinkCoroutine != null) StopCoroutine(blinkCoroutine);
        image.color = originalColor;
    }

    private IEnumerator Blink()
    {
        while (true)
        {
            image.color = Color.skyBlue;
            yield return new WaitForSeconds(0.3f);
            image.color = originalColor;
            yield return new WaitForSeconds(0.3f);
        }
    }
}