using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;

public class InitialSelection : MonoBehaviour
{
    [SerializeField] private GameObject firstButton;

    void Start()
    {
        EventSystem.current.SetSelectedGameObject(firstButton);
    }


}