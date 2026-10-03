using UnityEngine;

public class Water_SE : MonoBehaviour
{
    public AudioClip splashSound;  // 鳴らしたい効果音
    private AudioSource audioSource;

    void Start()
    {
        audioSource = GetComponent<AudioSource>();
    }

    private void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("Player"))
        {
            audioSource.PlayOneShot(splashSound);
        }
    }
}